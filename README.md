# Simple Python ZFS exporter for Prometheus

This is a simple ZFS exporter as provider for the [Prometheus  time series database
and monitoring system](https://prometheus.io/) written in Python. It uses
the [prometheus-client](https://github.com/prometheus/client_python) Python
package to do the main work of running the webservice and managing the gauges.
It's just a wrapper that periodically calls the ```zfs list``` and ```zpool status```
commands to gather information about the filesystems and the pools which is then
provided on the specified TCP port where it's collected by Prometheus at the
specified scrape interval. Note that this exporter does only scrape the filesystem
properties at a configurable interval instead at the query time of the time
series database itself.

Since this exporter scrapes the output of the CLI tools it may break with
any software update and might only work with particular versions of those
tools. It has been tested on:

* FreeBSD 11.2
* FreeBSD 12.2

## Exported metrics

* For each ZFS filesystem (```filesystem``` used as label):
   * Used bytes (```zfs_used```)
   * Available bytes (```zfs_avail```)
   * Referred bytes (```zfs_referred```)
* For each pool (```pool``` used as label):
   * Resilvered percentage (```zpoolResilvered```)
   * Resilvered bytes (```zpoolResilveredByte```)
   * Scrub scanned bytes (```zpoolScrubScanned```)
   * Scrub datarate (```zpool_scrub_rate```)
   * Scrub scanned percentage (```zpool_scrub_scanned_pct```)
* For each ```vdev``` (```vdev``` used as label):
   * Read errors (```zpoolErrorRead```)
   * Write errors (```zpoolErrorWrite```)
   * Checksum errors (```zpoolErrorChecksum```)
   * Operations read (```zpool_opread```)
   * Operations write (```zpool_opwrite```)
   * Bandwidth read (```zpool_bwread```)
   * Bandwidth write (```zpool_bwwrite```)
* For each non terminal ```vdev``` (```vdev``` used as label):
   * Allocated capacity (```zpool_capacityallocated```)
   * Free capacity (```zpool_capacityfree```)

## Installation

The package can either be installed from PyPI

```
pip install zfsexporter-tspspi
```

or form a package downloaded directly from the ```tar.gz``` or ```whl``` from
the [releases](https://github.com/tspspi/gammacli/releases):

```
pip install zfsexporter-tspspi.tar.gz
```

## Usage

```
usage: zfsexporter [-h] [-f] [--uid UID] [--gid GID] [--chroot CHROOT] [--pidfile PIDFILE] [--loglevel LOGLEVEL] [--logfile LOGFILE] [--port PORT] [--interval INTERVAL]

ZFS exporter daemon

optional arguments:
  -h, --help           show this help message and exit
  -f, --foreground     Do not daemonize - stay in foreground and dump debug information to the terminal
  --uid UID            User ID to impersonate when launching as root
  --gid GID            Group ID to impersonate when launching as root
  --chroot CHROOT      Chroot directory that should be switched into
  --pidfile PIDFILE    PID file to keep only one daemon instance running
  --loglevel LOGLEVEL  Loglevel to use (debug, info, warning, error, critical). Default: error
  --logfile LOGFILE    Logfile that should be used as target for log messages
  --port PORT          Port to listen on
  --interval INTERVAL  Interval in seconds in which data is gathered
```
