import plistlib
import pathlib
import unittest


INFO_PLIST_PATH = pathlib.Path(__file__).resolve().parents[1] / "workflow" / "info.plist"


class WorkflowConfigTests(unittest.TestCase):
    def test_action_connections_close_alfred_window(self):
        with INFO_PLIST_PATH.open("rb") as plist_file:
            workflow_config = plistlib.load(plist_file)

        connections = workflow_config["connections"]
        connection_configs = [
            connection
            for workflow_connections in connections.values()
            for connection in workflow_connections
        ]

        self.assertGreater(len(connection_configs), 0)
        self.assertTrue(
            all(connection["vitoclose"] is False for connection in connection_configs)
        )


if __name__ == "__main__":
    unittest.main()
