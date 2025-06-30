# Integration domain identifier
DOMAIN = "tper_tracker"

# TPER API base URL and endpoint URLs
BASE_API_URL = "https://webus.bo.it/app"
STOP_SEARCH_URL = f"{BASE_API_URL}/getSelect.php"
STOP_LINES_URL = f"{BASE_API_URL}/getLinee.php"
REAL_TIME_URL = f"{BASE_API_URL}/getRealTime.php"

# Configuration entry keys
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_LINE_IDS = "line_ids"
CONF_LINE_NAMES = "line_names"

# API and update timing configuration
API_TIMEOUT = 10
UPDATE_INTERVAL = 60

# Rate limiting and concurrency settings
DEFAULT_RATE_LIMIT_CALLS_PER_SECOND = 2.0
DEFAULT_MAX_CONCURRENT_REQUESTS = 2
MINIMUM_UPDATE_INTERVAL = 30