# AutoOrthoLogger
AutoOrther Logger for Linux

Collects AutoOrtho, X-Plane logs as well as the current lat/lon and altitude of your aircraft in X-P{lane and AutoOrtho, X-Plane and System Memory and places in a unified logs

Logs OS and Python verisons and scenery_packs.ini files in the unified file as well, as required for troubleshooting.

NOTE: Have leveraged on Gemini to produce, but tool might be useful to some.

USAGE:
IN X-Plane, go to Settings->Data Output
* Under Network Configuration set IP Address to 127.0.0.1 abd POrt to 49003
* Under General Data Output type altitude in the search box and select 'Network via UDP for Latitude, Longitude and altitude (Inder 20)

run the logger by:
>python AutoOrthoLogger.py

compress it all with:
>tar -czvf flight_logs.tar.gz xp_debug_unified.log
