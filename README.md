# Simple Python ZFS exporter for Prometheus

This is a simple ZFS exporter as provider for the [Prometheus  time series database
and monitoring system](https://prometheus.io/) written in Python. It uses
the [prometheus-client](https://github.com/prometheus/client_python) Python
package to do the main work of running the webservice and managing the gauges.
It's just a wrapper that periodically calls the ```zfs list``` and ```zpool status```
commands to gather information about the filesystems and the pools which is then
provided on the specified TCP port where it's collected by Prometheus at the
specified scrape interval. Note that this exporter does - against usual
recommendations - also only scrapes the filesystem properties at a configurable
interval instead at the query time of the time series database itself. This
might change in a later version due to obvious reasons.

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

## Usage
