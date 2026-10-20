# Integration domain identifier
DOMAIN = "tper_tracker"

# TPER Hello Bus real-time endpoint (one stop and one line per request)
HELLOBUS_URL = "https://hellobuswsweb.tper.it/web-services/hellobus.asmx/QueryHellobus"

# TPER open-data portal and the stop/line dataset used for search and line lists
OPEN_DATA_URL = "https://solweb.tper.it/web/tools/open-data"
STOPS_DATASET = "lineefermate"

# Identifies this integration to TPER
USER_AGENT = "ha-tper-tracker (+https://github.com/ddrimus/ha-tper-tracker)"

# Timezone of the times reported by TPER
TPER_TIME_ZONE = "Europe/Rome"

# Configuration entry keys
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_LINES = "lines"

# API and update timing configuration (seconds)
API_TIMEOUT = 10
DATASET_TIMEOUT = 60
UPDATE_INTERVAL = 60

# Polling interval when no bus is due and recheck interval for lines not served
IDLE_UPDATE_INTERVAL = 300
NOT_SERVED_RECHECK = 3600

# Rate limit protection, as TPER locks an IP after about 190 requests in a few minutes
REQUEST_SPACING = 2.0
LOCK_BACKOFF = 600

# How long the downloaded stop directory is trusted before checking for a newer version
STOPS_MAX_AGE = 7 * 24 * 3600

# How often each entry checks that its stop is still in the TPER stop list
STOP_CHECK_INTERVAL = 24 * 3600

# Maximum number of lines that can be tracked per stop
MAX_LINES = 20
