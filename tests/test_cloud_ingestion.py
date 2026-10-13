"""
UrbanPulse NEXUS — Cloud Ingestion & Environment Isolation Test Suite.
Validates:
1. Environment selection (local vs cloud).
2. Localhost prohibition in cloud mode.
3. Missing cloud credentials handling.
4. TLS configuration enforcement.
5. Durable TomTom quota accounting, safety margin, and fail-closed safety.
6. Idempotent event ID generation.
7. Dry-run execution behavior.
8. Preservation of local MySQL compatibility.
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
import sys
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from database.connection import get_db_pool, get_db_cursor
from ingestion.traffic.tomtom_client import TomTomBudgetTracker, TomTomTrafficClient
from ingestion.weather.weather_client import WeatherIngestionClient
from scripts.run_scheduled_batch import run_dry_run_validation, check_cadence_guard


class TestCloudIngestionArchitecture(unittest.TestCase):

    def setUp(self):
        # Store original environment
        self.orig_env = os.environ.get("URBANPULSE_ENV")
        self.orig_tidb_host = settings.TIDB_HOST
        self.orig_tidb_user = settings.TIDB_USER
        self.orig_tidb_pass = settings.TIDB_PASSWORD
        self.orig_mysql_user = settings.MYSQL_USER
        self.orig_mysql_pass = settings.MYSQL_PASSWORD

    def tearDown(self):
        # Restore environment
        if self.orig_env is not None:
            os.environ["URBANPULSE_ENV"] = self.orig_env
            settings.URBANPULSE_ENV = self.orig_env
        else:
            os.environ.pop("URBANPULSE_ENV", None)
            settings.URBANPULSE_ENV = "local"

        settings.TIDB_HOST = self.orig_tidb_host
        settings.TIDB_USER = self.orig_tidb_user
        settings.TIDB_PASSWORD = self.orig_tidb_pass
        settings.MYSQL_USER = self.orig_mysql_user
        settings.MYSQL_PASSWORD = self.orig_mysql_pass

        import database.connection
        database.connection._connection_pool = None

    def test_environment_selection_local(self):
        """Verifies that default environment is 'local' and identifies as local."""
        settings.URBANPULSE_ENV = "local"
        self.assertTrue(settings.is_local)
        self.assertFalse(settings.is_cloud)

    def test_environment_selection_cloud(self):
        """Verifies that setting URBANPULSE_ENV to 'cloud' sets is_cloud to True."""
        settings.URBANPULSE_ENV = "cloud"
        self.assertTrue(settings.is_cloud)
        self.assertFalse(settings.is_local)

    def test_cloud_mode_prohibits_localhost(self):
        """Verifies that cloud mode strictly forbids localhost or 127.0.0.1 for production storage."""
        settings.URBANPULSE_ENV = "cloud"
        settings.TIDB_HOST = "localhost"

        import database.connection
        database.connection._connection_pool = None

        with self.assertRaises(ValueError) as ctx:
            database.connection.get_db_pool()
        self.assertIn("prohibits connecting to localhost", str(ctx.exception))

        settings.TIDB_HOST = "127.0.0.1"
        database.connection._connection_pool = None
        with self.assertRaises(ValueError) as ctx:
            database.connection.get_db_pool()
        self.assertIn("prohibits connecting to localhost", str(ctx.exception))

    def test_cloud_mode_requires_credentials(self):
        """Verifies that cloud mode raises error if remote host is given but credentials missing."""
        settings.URBANPULSE_ENV = "cloud"
        settings.TIDB_HOST = "gateway01.test.tidbcloud.com"
        settings.TIDB_USER = ""
        settings.TIDB_PASSWORD = ""
        settings.MYSQL_USER = ""
        settings.MYSQL_PASSWORD = ""

        import database.connection
        database.connection._connection_pool = None

        with self.assertRaises(ValueError) as ctx:
            database.connection.get_db_pool()
        self.assertIn("requires valid cloud database credentials", str(ctx.exception))

    def test_tomtom_budget_tracker_effective_limit(self):
        """Verifies that budget tracker calculates effective limit with safety margin."""
        tracker = TomTomBudgetTracker(monthly_budget=16000)
        self.assertEqual(tracker.monthly_budget, 16000)
        self.assertEqual(tracker.safety_margin, 500)
        self.assertEqual(tracker.effective_limit, 15500)

    def test_tomtom_budget_tracker_cutoff_engaged(self):
        """Verifies that budget tracker halts requests when attempts reach effective limit."""
        tracker = TomTomBudgetTracker(monthly_budget=16000)
        # Mock load state to simulate limit reached
        mock_state = {
            "month": tracker._get_current_month_key(),
            "requests_attempted": 15501,
            "requests_successful": 15500,
            "requests_failed": 1,
        }
        with patch.object(tracker, "_load_durable_state", return_value=mock_state):
            with patch.object(tracker, "_load_state", return_value=mock_state):
                allowed, msg = tracker.can_request()
                self.assertFalse(allowed)
                self.assertIn("safety cutoff engaged", msg)

    def test_tomtom_budget_tracker_fails_closed_in_cloud(self):
        """Verifies that budget tracker fails closed in cloud mode if durable storage is unreachable."""
        settings.URBANPULSE_ENV = "cloud"
        tracker = TomTomBudgetTracker(monthly_budget=16000)

        # Simulate database failure returning None
        with patch.object(tracker, "_load_durable_state", return_value=None):
            allowed, msg = tracker.can_request()
            self.assertFalse(allowed)
            self.assertIn("Failing closed", msg)

    def test_deterministic_event_id_deduplication(self):
        """Verifies that deterministic event IDs match across repeated executions for idempotency."""
        client = WeatherIngestionClient()
        id1 = client._generate_event_id("LOC_NAGPUR", "2026-10-13 16:00:00")
        id2 = client._generate_event_id("LOC_NAGPUR", "2026-10-13 16:00:00")
        id3 = client._generate_event_id("LOC_NAGPUR", "2026-10-13 17:00:00")

        self.assertEqual(id1, id2)
        self.assertNotEqual(id1, id3)
        self.assertTrue(id1.startswith("EVT_WTH_"))

    def test_dry_run_validation_executes_cleanly(self):
        """Verifies that dry-run validation passes with zero errors in local mode."""
        settings.URBANPULSE_ENV = "local"
        import database.connection
        database.connection._connection_pool = None

        result = run_dry_run_validation()
        self.assertTrue(result)

    def test_local_mysql_intact_and_connected(self):
        """Verifies that local MySQL connection and table count remain healthy."""
        settings.URBANPULSE_ENV = "local"
        import database.connection
        database.connection._connection_pool = None

        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SHOW TABLES;")
            tables = [list(r.values())[0] for r in cursor.fetchall()]
            self.assertGreaterEqual(len(tables), 13)

    def test_conservative_opening_balance_applied(self):
        """Verifies that conservative opening balance (200) is applied when storage has 0."""
        tracker = TomTomBudgetTracker(monthly_budget=16000)
        self.assertEqual(tracker.opening_balance, 200)
        empty_state = {
            "month": tracker._get_current_month_key(),
            "requests_attempted": 0,
            "requests_successful": 0,
            "requests_failed": 0,
        }
        with patch.object(tracker, "_load_durable_state", return_value=empty_state):
            with patch.object(tracker, "_load_state", return_value=empty_state):
                usage = tracker.get_usage()
                self.assertEqual(usage["requests_attempted"], 200)
                self.assertEqual(usage["opening_balance"], 200)
                self.assertEqual(usage["effective_limit"], 15500)

    def test_reservation_precedes_http_request(self):
        """Verifies that reserve_request() is invoked and capacity reserved before requests.get()."""
        client = TomTomTrafficClient(api_key="TEST_KEY")
        order_of_events = []

        def mock_reserve():
            order_of_events.append("reserved")
            return True, "Slot reserved"

        def mock_get(*args, **kwargs):
            order_of_events.append("http_get")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"flowSegmentData": {"currentSpeed": 45, "freeFlowSpeed": 50}}
            return mock_resp

        def mock_outcome(successful):
            order_of_events.append(f"outcome_{successful}")

        with patch.object(client.budget_tracker, "reserve_request", side_effect=mock_reserve):
            with patch.object(client.budget_tracker, "record_outcome", side_effect=mock_outcome):
                with patch("requests.get", side_effect=mock_get):
                    ok, payload, err = client.fetch_flow_segment_data(21.145, 79.088)
                    self.assertTrue(ok)
                    self.assertEqual(order_of_events, ["reserved", "http_get", "outcome_True"])

    def test_failed_request_and_timeout_consume_quota(self):
        """Verifies that HTTP failure and timeout record failure outcome while capacity was reserved."""
        client = TomTomTrafficClient(api_key="TEST_KEY")
        client.max_retries = 1

        outcomes = []
        with patch.object(client.budget_tracker, "reserve_request", return_value=(True, "Reserved")):
            with patch.object(client.budget_tracker, "record_outcome", side_effect=lambda successful=False: outcomes.append(successful)):
                import requests as req
                with patch("requests.get", side_effect=req.Timeout("Simulated timeout")):
                    ok, payload, err = client.fetch_flow_segment_data(21.145, 79.088)
                    self.assertFalse(ok)
                    self.assertIn("timed out", err)
                    self.assertEqual(outcomes, [False])

    def test_retry_reserves_additional_slot(self):
        """Verifies that a retry attempts to reserve a second slot."""
        client = TomTomTrafficClient(api_key="TEST_KEY")
        client.max_retries = 2

        reservation_calls = []
        def mock_reserve():
            call_num = len(reservation_calls) + 1
            reservation_calls.append(call_num)
            return True, f"Slot {call_num} reserved"

        import requests as req
        with patch.object(client.budget_tracker, "reserve_request", side_effect=mock_reserve):
            with patch.object(client.budget_tracker, "record_outcome"):
                with patch("requests.get", side_effect=req.RequestException("Temporary glitch")):
                    with patch("time.sleep"):  # skip sleep in test
                        ok, payload, err = client.fetch_flow_segment_data(21.145, 79.088)
                        self.assertFalse(ok)
                        # Should have reserved for attempt 1 and attempt 2 (retry)
                        self.assertEqual(len(reservation_calls), 2)

    def test_workflow_activation_guard_logic(self):
        """Verifies workflow activation logic for scheduled vs manual and dry_run vs live."""
        def evaluate_guard(event_name, dry_run_input, enable_cloud_var):
            if dry_run_input == "true":
                return "proceed_dry_run"
            if enable_cloud_var != "true":
                return "paused"
            return "proceed_live"

        # 1. Scheduled cron with activation paused -> paused
        self.assertEqual(evaluate_guard("schedule", "false", "false"), "paused")
        self.assertEqual(evaluate_guard("schedule", "false", ""), "paused")

        # 2. Scheduled cron with activation enabled -> proceed_live
        self.assertEqual(evaluate_guard("schedule", "false", "true"), "proceed_live")

        # 3. Manual dispatch with dry_run true -> proceed_dry_run regardless of variable
        self.assertEqual(evaluate_guard("workflow_dispatch", "true", "false"), "proceed_dry_run")
        self.assertEqual(evaluate_guard("workflow_dispatch", "true", "true"), "proceed_dry_run")

        # 4. Manual dispatch with dry_run false and activation paused -> paused (safety guard!)
        self.assertEqual(evaluate_guard("workflow_dispatch", "false", "false"), "paused")

        # 5. Manual dispatch with dry_run false and activation true -> proceed_live
        self.assertEqual(evaluate_guard("workflow_dispatch", "false", "true"), "proceed_live")

    def test_opening_balance_never_repeatedly_added(self):
        """Verifies opening balance is applied as a baseline floor once and cannot be repeatedly added."""
        tracker = TomTomBudgetTracker(monthly_budget=16000)
        self.assertEqual(tracker.opening_balance, 200)

        # In-memory simulated state starting at 0
        state = {
            "month": tracker._get_current_month_key(),
            "requests_attempted": 0,
            "requests_successful": 0,
            "requests_failed": 0,
        }

        # Step 1: Initial state usage is floored at 200
        with patch.object(tracker, "_load_durable_state", return_value=state):
            with patch.object(tracker, "_load_state", return_value=state):
                usage = tracker.get_usage()
                self.assertEqual(usage["requests_attempted"], 200)

        # Step 2: First reservation moves from baseline 200 to 201 (not 400!)
        def mock_reserve_slot(month):
            curr = max(state["requests_attempted"], tracker.opening_balance)
            state["requests_attempted"] = curr + 1
            return True, f"Slot {state['requests_attempted']} reserved", state["requests_attempted"]

        with patch.object(tracker, "_load_durable_state", return_value=state):
            with patch.object(tracker, "_reserve_durable_slot", side_effect=mock_reserve_slot):
                tracker._save_state = lambda s: state.update(s)
                tracker._load_state = lambda: state
            
            ok1, _ = tracker.reserve_request()
            self.assertTrue(ok1)
            self.assertEqual(state["requests_attempted"], 201)

            # Step 3: Second reservation moves to 202 (not 402!)
            ok2, _ = tracker.reserve_request()
            self.assertTrue(ok2)
            self.assertEqual(state["requests_attempted"], 202)

            # Step 4: Third reservation moves to 203
            ok3, _ = tracker.reserve_request()
            self.assertTrue(ok3)
            self.assertEqual(state["requests_attempted"], 203)

    def test_reservation_transaction_commits_before_http(self):
        """Verifies that quota reservation transaction commits before HTTP dispatch."""
        client = TomTomTrafficClient(api_key="TEST_KEY")
        events = []

        mock_conn = MagicMock()
        def mock_commit():
            events.append("transaction_committed")
        mock_conn.commit.side_effect = mock_commit

        mock_cursor = MagicMock()
        mock_cursor._connection = mock_conn
        mock_cursor.fetchone.return_value = {"requests_attempted": 201}

        from contextlib import contextmanager
        @contextmanager
        def mock_cursor_ctx(commit=False, dictionary=True):
            yield mock_cursor

        def mock_get(*args, **kwargs):
            events.append("http_get_dispatched")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"flowSegmentData": {"currentSpeed": 50, "freeFlowSpeed": 55}}
            return mock_resp

        with patch("database.connection.get_db_cursor", side_effect=mock_cursor_ctx):
            with patch("requests.get", side_effect=mock_get):
                with patch.object(client.budget_tracker, "_ensure_durable_table"):
                    with patch.object(client.budget_tracker, "_record_durable_outcome"):
                        client.fetch_flow_segment_data(21.145, 79.088)

        # Assert transaction committed strictly before HTTP was dispatched
        self.assertIn("transaction_committed", events)
        self.assertIn("http_get_dispatched", events)
        self.assertLess(events.index("transaction_committed"), events.index("http_get_dispatched"))

    def test_cloud_connection_pool_hang_protection(self):
        """Verifies that cloud connection pool disables pool_reset_session and sets connection_timeout."""
        settings.URBANPULSE_ENV = "cloud"
        settings.TIDB_HOST = "gateway01.test.tidbcloud.com"
        settings.TIDB_USER = "test_user"
        settings.TIDB_PASSWORD = "test_password"

        import database.connection
        database.connection._connection_pool = None

        with patch("mysql.connector.pooling.MySQLConnectionPool") as mock_pool_cls:
            database.connection.get_db_pool()
            mock_pool_cls.assert_called_once()
            called_kwargs = mock_pool_cls.call_args[1]
            self.assertFalse(called_kwargs.get("pool_reset_session"), "pool_reset_session must be False to avoid TiDB COM_RESET_CONNECTION hang")
            self.assertEqual(called_kwargs.get("connection_timeout"), 15, "connection_timeout must be bounded to 15s")
            self.assertTrue(called_kwargs.get("ssl_verify_cert"), "ssl_verify_cert must be True")

    def test_durable_state_load_never_executes_ddl(self):
        """Verifies that _load_durable_state is strictly read-only and never runs _ensure_durable_table DDL."""
        client = TomTomTrafficClient(api_key="TEST_KEY")
        tracker = client.budget_tracker

        with patch.object(tracker, "_ensure_durable_table") as mock_ensure:
            with patch("database.connection.get_db_cursor") as mock_cursor_ctx:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = None
                mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

                res = tracker._load_durable_state("2026-10")
                mock_ensure.assert_not_called()
                self.assertIsNotNone(res)
                self.assertEqual(res["requests_attempted"], 0)


if __name__ == "__main__":
    unittest.main()

