#!/usr/bin/env python3

import argparse
import sys
import logging

import signal, lockfile, grp, os

from pwd import getpwnam
from daemonize import Daemonize

from prometheus_client import start_http_server, Gauge
from typing import Dict
import subprocess
import time

class ZFSExporterDaemon:
	def __init__(self, args, logger):
		self.args = args
		self.logger = logger
		self.terminate = False
		self.rereadConfig = True

		self.metrics = {
			'zfsUsed' : Gauge(
				"zfs_used", "Used bytes", labelnames = [ 'filesystem' ]
			),
			'zfsAvail' : Gauge(
				"zfs_avail", "Available bytes", labelnames = [ 'filesystem' ]
			),
			'zfsReferred' : Gauge(
				"zfs_referred", "Referred bytes", labelnames = [ 'filesystem' ]
			),

			'zpoolCapacityAlloc' : Gauge(
				"zpool_capacityallocated", "Allocated capacity", labelnames = [ 'vdev' ]
			),
			'zpoolCapacityFree' : Gauge(
				"zpool_capacityfree", "Available (free) capacity", labelnames = [ 'vdev' ]
			),
			'zpoolOperationsRead' : Gauge(
				"zpool_opread", "Operations read", labelnames = [ 'vdev' ]
			),
			'zpoolOperationsWrite' : Gauge(
				"zpool_opwrite", "Operations write", labelnames = ['vdev']
			),
			'zpoolBandwidthRead' : Gauge(
				"zpool_bwread", "Bandwidth read", labelnames = [ 'vdev' ]
			),
			'zpoolBandwidthWrite' : Gauge(
				"zpool_bwwrite", "Bandwidth write", labelnames = [ 'vdev' ]
			),
			'zpoolErrorRead' : Gauge(
				"zpool_errorread", "Read errors", labelnames = [ 'vdev' ]
			),
			'zpoolErrorWrite' : Gauge(
				"zpool_errorwrite", "Write errors", labelnames = [ 'vdev' ]
			),
			'zpoolErrorChecksum' : Gauge(
				"zpool_errorchecksum", "Checksum errors", labelnames = [ 'vdev' ]
			),

			'zpoolResilvered' : Gauge(
				"zpool_resilvered_pct", "Percentage of resilvering done", labelnames = [ 'pool' ]
			),
			'zpoolResilveredByte' : Gauge(
				"zpool_resilvered_bytes", "Bytes resilvered", labelnames = [ 'pool' ]
			),
			'zpoolScrubScanned' : Gauge(
				"zpool_scrub_scanned", "Bytes scanned during scrub", labelnames = [ 'pool' ]
			),
			'zpoolScrubDatarate' : Gauge(
				"zpool_scrub_rate", "Datarate of scrub", labelnames = [ 'pool' ]
			),
			'zpoolScrubScannedPct' : Gauge(
				"zpool_scrub_scanned_pct", "Percentage currently scanned", labelnames = [ 'pool' ]
			)
		}

	def SuffixNotationToBytes(self, inp):
		if inp[-1] == 'K':
			return float(inp[:-1]) * 1e3
		if inp[-1] == 'M':
			return float(inp[:-1]) * 1e6
		if inp[-1] == 'G':
			return float(inp[:-1]) * 1e9
		if inp[-1] == 'T':
			return float(inp[:-1]) * 1e12
		else:
			return float(inp)

	def parseZPOOLIostat(self, metrics):
		p = subprocess.Popen("zpool iostat -v", stdout=subprocess.PIPE, shell=True)
		(output, err) = p.communicate()
		status = p.wait()

		output = output.decode("utf-8").split("\n")

		for i in range(len(output)):
			output[i] = output[i].strip()

		knownVdevs = []

		for i in range(3, len(output)):
			if output[i].startswith("----"):
				continue

			line = output[i]
			line = line.split()

			if(len(line) == 7):
				# We seem to be able to handle that ...

				vdevname = line[0]
				knownVdevs.append(vdevname)

				if line[1] != '-':
					capacityAlloc = self.SuffixNotationToBytes(line[1])
					self.metrics['zpoolCapacityAlloc'].labels(vdevname).set(capacityAlloc)
				if line[2] != '-':
					capacityFree = self.SuffixNotationToBytes(line[2])
					self.metrics['zpoolCapacityFree'].labels(vdevname).set(capacityFree)
				if line[3] != '-':
					opread = self.SuffixNotationToBytes(line[3])
					self.metrics['zpoolOperationsRead'].labels(vdevname).set(opread)
				if line[4] != '-':
					opwrite = self.SuffixNotationToBytes(line[4])
					self.metrics['zpoolOperationsWrite'].labels(vdevname).set(opwrite)
				if line[5] != '-':
					bwread = self.SuffixNotationToBytes(line[5])
					self.metrics['zpoolBandwidthRead'].labels(vdevname).set(bwread)
				if line[6] != '-':
					bwwrite = self.SuffixNotationToBytes(line[6])
					self.metrics['zpoolBandwidthWrite'].labels(vdevname).set(bwwrite)

				self.logger.info("[ZPOOL-IOSTAT] {}: {} allocated, {} free, {} op.read, {} op.write, {} bw.read, {} bw.write".format(
					vdevname,
					capacityAlloc,
					capacityFree,
					opread,
					opwrite,
					bwread,
					bwwrite
				))

		p = subprocess.Popen("zpool status", stdout=subprocess.PIPE, shell=True)
		(output, err) = p.communicate()
		status = p.wait()
		output = output.decode("utf-8").split("\n")

		bHeaderDone = False
		currentPool = None
		currentResilverPct = 0
		currentResilverBytes = 0
		currentScrubScanned = 0
		currentScrubRate = 0
		currentScrubPct = 0
		currentScrubTotal = 0

		for i in range(len(output)):
			output[i] = output[i].strip()

			if output[i].startswith("pool: "):
				if currentPool:
					# Publish the previouses pool scrub and resilver values
					self.metrics['zpoolResilvered'].labels(currentPool).set(currentResilverPct)
					self.metrics['zpoolResilveredByte'].labels(currentPool).set(currentResilverBytes)
					self.metrics['zpoolScrubScanned'].labels(currentPool).set(currentScrubScanned)
					self.metrics['zpoolScrubDatarate'].labels(currentPool).set(currentScrubRate)
					self.metrics['zpoolScrubScannedPct'].labels(currentPool).set(currentScrubPct)

					self.logger.info("[ZPOOL-STATUS] {} resilvered {}% ({} bytes)".format(currentPool, currentResilverPct, currentResilverBytes))
					self.logger.info("[ZPOOL-STATUS] {} scrubed {}% ({} bytes) at {} bytes/sec".format(currentPool, currentScrubPct, currentScrubScanned, currentScrubRate))

					currentPool = None
				currentPool = output[i]
				currentPool = currentPool.split("pool: ")[1]
				currentPool = currentPool.strip()
			if "scanned out of" in output[i]:
				parts = output[i].split("scanned out of")
				currentScrubScanned = self.SuffixNotationToBytes(parts[0].strip())
				parts = parts[1].split(" at ")
				currentScrubTotal = self.SuffixNotationToBytes(parts[0].strip())
				currentScrubPct = currentScrubScanned / currentScrubTotal * 100.0
				parts = parts[1].split("/")
				currentScrubRate = self.SuffixNotationToBytes(parts[0].strip())
			if " resilvered, " in output[i]:
				parts = output[i].split(" resilvered, ")
				currentResilverBytes = self.SuffixNotationToBytes(parts[0].strip())
				parts = parts[1].split("%")
				currentResilverPct = float(parts[0].strip())

			if not bHeaderDone:
				if not output[i].startswith("NAME"):
					continue
				bHeaderDone = True
				continue

			line = output[i].split()

			if len(line) != 5:
				continue
			if line[0] == "errors:":
				break

			vdevname = line[0]
			state = line[1]
			readerror = self.SuffixNotationToBytes(line[2])
			writeerror = self.SuffixNotationToBytes(line[3])
			chksumerror = self.SuffixNotationToBytes(line[4])

			self.metrics['zpoolErrorRead'].labels(vdevname).set(readerror)
			self.metrics['zpoolErrorWrite'].labels(vdevname).set(writeerror)
			self.metrics['zpoolErrorChecksum'].labels(vdevname).set(chksumerror)

			self.logger.info("[ZPOOL-STATUS] {} ({}): {} read errors, {} write errors, {} checksum errors".format(vdevname, state, readerror, writeerror, chksumerror))

		if currentPool:
			# Publish the previouses pool scrub and resilver values
			self.metrics['zpoolResilvered'].labels(currentPool).set(currentResilverPct)
			self.metrics['zpoolResilveredByte'].labels(currentPool).set(currentResilverBytes)
			self.metrics['zpoolScrubScanned'].labels(currentPool).set(currentScrubScanned)
			self.metrics['zpoolScrubDatarate'].labels(currentPool).set(currentScrubRate)
			self.metrics['zpoolScrubScannedPct'].labels(currentPool).set(currentScrubPct)

			self.logger.info("[ZPOOL-STATUS] {} resilvered {}% ({} bytes)".format(currentPool, currentResilverPct, currentResilverBytes))
			self.logger.info("[ZPOOL-STATUS] {} scrubed {}% ({} bytes) at {} bytes/sec".format(currentPool, currentScrubPct, currentScrubScanned, currentScrubRate))

			currentPool = None

	def parseZFSList(self, metrics):
		p = subprocess.Popen("zfs list", stdout=subprocess.PIPE, shell=True)
		(output, err) = p.communicate()
		status = p.wait()

		output = output.decode("utf-8").split("\n")
		for i in range(len(output)):
			output[i] = output[i].strip()

		for i in range(1, len(output)-1):
			line = output[i]
			line = line.split()

			fsName = line[0]
			usedBytes = self.SuffixNotationToBytes(line[1])
			availBytes = self.SuffixNotationToBytes(line[2])
			referredBytes = self.SuffixNotationToBytes(line[3])
			mountpoint = line[4]

			metrics['zfsUsed'].labels(fsName).set(usedBytes)
			metrics['zfsAvail'].labels(fsName).set(availBytes)
			metrics['zfsReferred'].labels(fsName).set(referredBytes)

			self.logger.info("[ZFS-FS] {}: {} used, {} avail, {} referred".format(fsName, usedBytes, availBytes, referredBytes))

	def signalSigHup(self, *args):
		self.rereadConfig = True
	def signalTerm(self, *args):
		self.terminate = True
	def __enter__(self):
		return self
	def __exit__(self, type, value, tb):
		pass

	def run(self):
		signal.signal(signal.SIGHUP, self.signalSigHup)
		signal.signal(signal.SIGTERM, self.signalTerm)
		signal.signal(signal.SIGINT, self.signalTerm)

		self.logger.info("Service running")

		start_http_server(self.args.port)
		while True:
			time.sleep(self.args.interval)
			self.parseZFSList(self.metrics)
			self.parseZPOOLIostat(self.metrics)

			if self.terminate:
				break

		self.logger.info("Shutting down due to user request")

def mainDaemon():
	parg = parseArguments()
	args = parg['args']
	logger = parg['logger']

	logger.debug("Daemon starting ...")
	with ZFSExporterDaemon(args, logger) as exporterDaemon:
		exporterDaemon.run()

def parseArguments():
	ap = argparse.ArgumentParser(description = 'ZFS exporter daemon')
	ap.add_argument('-f', '--foreground', action='store_true', help="Do not daemonize - stay in foreground and dump debug information to the terminal")

	ap.add_argument('--uid', type=str, required=False, default=None, help="User ID to impersonate when launching as root")
	ap.add_argument('--gid', type=str, required=False, default=None, help="Group ID to impersonate when launching as root")
	ap.add_argument('--chroot', type=str, required=False, default=None, help="Chroot directory that should be switched into")
	ap.add_argument('--pidfile', type=str, required=False, default="/var/run/zfsexporter.pid", help="PID file to keep only one daemon instance running")
	ap.add_argument('--loglevel', type=str, required=False, default="error", help="Loglevel to use (debug, info, warning, error, critical). Default: error")
	ap.add_argument('--logfile', type=str, required=False, default="/var/log/zfsexporter.log", help="Logfile that should be used as target for log messages")

	ap.add_argument('--port', type=int, required=False, default=9249, help="Port to listen on")
	ap.add_argument('--interval', type=int, required=False, default=30, help="Interval in seconds in which data is gathered")

	args = ap.parse_args()
	loglvls = {
		"DEBUG"     : logging.DEBUG,
		"INFO"      : logging.INFO,
		"WARNING"   : logging.WARNING,
		"ERROR"     : logging.ERROR,
		"CRITICAL"  : logging.CRITICAL
	}
	if not args.loglevel.upper() in loglvls:
		print("Unknown log level {}".format(args.loglevel.upper()))
		sys.exit(1)

	logger = logging.getLogger()
	logger.setLevel(loglvls[args.loglevel.upper()])
	if args.logfile:
		fileHandleLog = logging.FileHandler(args.logfile)
		logger.addHandler(fileHandleLog)

	return { 'args' : args, 'logger' : logger }

def mainStartup():
	parg = parseArguments()
	args = parg['args']
	logger = parg['logger']

	daemonPidfile = args.pidfile
	daemonUid = None
	daemonGid = None
	daemonChroot = "/"

	if args.uid:
		try:
			args.uid = int(args.uid)
		except ValueError:
			try:
				args.uid = getpwnam(args.uid).pw_uid
			except KeyError:
				logger.critical("Unknown user {}".format(args.uid))
				print("Unknown user {}".format(args.uid))
				sys.exit(1)
		daemonUid = args.uid
	if args.gid:
		try:
			args.gid = int(args.gid)
		except ValueError:
			try:
				args.gid = grp.getgrnam(args.gid)[2]
			except KeyError:
				logger.critical("Unknown group {}".format(args.gid))
				print("Unknown group {}".format(args.gid))
				sys.exit(1)

		daemonGid = args.gid

	if args.chroot:
		if not os.path.isdir(args.chroot):
			logger.critical("Non existing chroot directors {}".format(args.chroot))
			print("Non existing chroot directors {}".format(args.chroot))
			sys.exit(1)
		daemonChroot = args.chroot

	if args.foreground:
		logger.debug("Launching in foreground")
		with ZFSExporterDaemon(args, logger) as zfsDaemon:
			zfsDaemon.run()
	else:
		logger.debug("Daemonizing ...")
		daemon = Daemonize(
			app="ZFS exporter",
			action=mainDaemon,
			pid=daemonPidfile,
			user=daemonUid,
			group=daemonGid,
			chdir=daemonChroot
		)
		daemon.start()


if __name__ == "__main__":
	mainStartup()
