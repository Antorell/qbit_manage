"""Class to handle webhooks."""
from json import JSONDecodeError

from requests.exceptions import JSONDecodeError as requestsJSONDecodeError

from modules import util
from modules.util import Failed

logger = util.logger


class Webhooks:
    """Class to handle webhooks."""

    def __init__(self, config, system_webhooks, notifiarr=None, apprise=None):
        """Initialize the class."""
        self.config = config
        self.error_webhooks = system_webhooks["error"] if "error" in system_webhooks else []
        self.run_start_webhooks = system_webhooks["run_start"] if "run_start" in system_webhooks else []
        self.run_end_webhooks = system_webhooks["run_end"] if "run_end" in system_webhooks else []
        if "function" in system_webhooks and system_webhooks["function"] is not None:
            try:
                self.function_webhooks = system_webhooks["function"][0]
            except (IndexError, KeyError):
                self.function_webhooks = []
        else:
            self.function_webhooks = []
        self.notifiarr = notifiarr
        self.apprise = apprise

    def _request(self, webhooks, json):
        """Send a webhook request."""
        logger.trace("")
        logger.trace(f"JSON: {json}")
        for webhook in list(set(webhooks)):
            response = None
            logger.trace(f"Webhook: {webhook}")
            if webhook is None:
                break
            elif webhook == "notifiarr":
                if self.notifiarr is None:
                    break
                else:
                    response = self.notifiarr.notification(json=json)
                    if response.status_code < 500:
                        break
            elif webhook == "apprise":
                if self.apprise is None:
                    logger.warning("Webhook attribute set to apprise but apprise attribute is not configured.")
                    break
                else:
                    json["urls"] = self.apprise.notify_url
                    response = self.config.post(f"{self.apprise.api_url}/notify", json=json)
                    if response.status_code < 500:
                        break
            else:
                response = self.config.post(webhook, json=json)
            if response:
                skip = False
                try:
                    response_json = response.json()
                    logger.trace(f"Response: {response_json}")
                    if (
                        "result" in response_json
                        and response_json["result"] == "error"
                        and "details" in response_json
                        and "response" in response_json["details"]
                    ):
                        if "trigger is not enabled" in response_json["details"]["response"]:
                            logger.debug(f"Notifiarr Warning: {response_json['details']['response']}")
                            skip = True
                        else:
                            raise Failed(f"Notifiarr Error: {response_json['details']['response']}")
                    if (
                        response.status_code >= 400 or ("result" in response_json and response_json["result"] == "error")
                    ) and skip is False:
                        raise Failed(f"({response.status_code} [{response.reason}]) {response_json}")
                except (JSONDecodeError, requestsJSONDecodeError) as exc:
                    if response.status_code >= 400:
                        raise Failed(f"({response.status_code} [{response.reason}])") from exc

    def start_time_hooks(self, start_time):
        """Send a webhook to notify that the run has started."""
        if self.run_start_webhooks:
            dry_run = self.config.commands["dry_run"]
            if dry_run:
                start_type = "Dry-"
            else:
                start_type = ""
            self._request(
                self.run_start_webhooks,
                {
                    "function": "run_start",
                    "title": None,
                    "body": f"Starting {start_type}Run",
                    "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "dry_run": self.config.commands["dry_run"],
                },
            )

    def end_time_hooks(self, start_time, end_time, run_time, next_run, stats, body):
        """Send a webhook to notify that the run has ended."""
        if self.run_end_webhooks:
            self._request(
                self.run_end_webhooks,
                {
                    "function": "run_end",
                    "title": None,
                    "body": body,
                    "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run is not None else next_run,
                    "run_time": run_time,
                    "torrents_added": stats["added"],
                    "torrents_deleted": stats["deleted"],
                    "torrents_deleted_and_contents_count": stats["deleted_contents"],
                    "torrents_resumed": stats["resumed"],
                    "torrents_rechecked": stats["rechecked"],
                    "torrents_categorized": stats["categorized"],
                    "torrents_tagged": stats["tagged"],
                    "remove_unregistered": stats["rem_unreg"],
                    "torrents_tagged_tracker_error": stats["tagged_tracker_error"],
                    "torrents_untagged_tracker_error": stats["untagged_tracker_error"],
                    "orphaned_files_found": stats["orphaned"],
                    "torrents_tagged_no_hardlinks": stats["tagged_noHL"],
                    "torrents_untagged_no_hardlinks": stats["untagged_noHL"],
                    "files_deleted_from_recyclebin": stats["recycle_emptied"],
                    "files_deleted_from_orphaned": stats["orphaned_emptied"],
                },
            )

    def error_hooks(self, text, function_error=None, critical=True):
        """Send a webhook to notify that an error has occurred."""
        if self.error_webhooks:
            err_type = "failure" if critical is True else "warning"
            json = {
                "function": "run_error",
                "title": f"{function_error} Error",
                "body": str(text),
                "critical": critical,
                "type": err_type,
            }
            if function_error:
                json["function_error"] = function_error
            self._request(self.error_webhooks, json)

    def function_hooks(self, webhook, json):
        """Send a webhook to notify that a function has completed."""
        if self.function_webhooks:
            self._request(webhook, json)
