import time
from typing import Any
import yaml
import webbrowser
import json
import datetime
import logging
from pathlib import Path
from dataclasses import dataclass

import requests
from garth.exc import GarthHTTPError
import garminconnect

import urllib.parse
import threading, queue
from flask import Flask, request
from werkzeug.datastructures import MultiDict

import os

UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 0))
PORT = int(os.getenv("WITHINGS_PORT", 5681))
log_level = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=logging._nameToLevel[log_level])
logger = logging.getLogger("wt_gc_bridge")

app = Flask(__name__)
code_queue: queue.Queue[MultiDict] = queue.Queue()


@app.route("/")
def get_token() -> str:
    code_queue.put(request.args)
    return "<p>Success!</p>"


@dataclass
class Measurement:
    datetime: datetime.datetime
    weight: float


class WithingsGCBridge:
    SECRETS = Path("secrets.yaml")
    tokenstore = ".tokenstore"
    withings_callback_uri: str = f"http://127.0.0.1:{PORT}"
    garmin: garminconnect.Garmin

    def __init__(self) -> None:
        try:
            with self.SECRETS.open() as F:
                secrets = yaml.safe_load(F)
        except Exception as err:
            logger.error(f"Could not load secrets.yaml")
            raise err

        try:
            self.withings_client_id = secrets["withings"]["client_id"]
            self.withings_client_secret = secrets["withings"]["secret"]
        except KeyError as err:
            logger.error(f"Could not load secrets.yaml")
            raise err

        if "callback_uri" in secrets["withings"]:
            self.withings_callback_uri = secrets["withings"]["callback_uri"]
        self.parsed_withings_uri = urllib.parse.urlparse(self.withings_callback_uri)
        logging.debug(f"Running flask endpoint {self.parsed_withings_uri}")
        # run flask endpoint
        threading.Thread(
            target=lambda: app.run(
                debug=False,
                host=self.parsed_withings_uri.hostname,
                port=self.parsed_withings_uri.port,
            ),
            daemon=True,
        ).start()

    def sync(self) -> None:
        garmin = self.init_garmin()
        withings_access_token = self.init_withings()

        last_sync_path = Path(".last_sync.txt")
        if not last_sync_path.exists():
            logger.info("Could not determine last sync date. Syncing last 7 days.")
            last_sync = datetime.datetime.now() - datetime.timedelta(days=7)
        else:
            with open(".last_sync.txt", "r") as F:
                last_sync = datetime.datetime.fromisoformat(F.read().strip())

        # 1) get weight with timestamp from withings
        weights = self.get_weight_from_withings(withings_access_token, last_sync)

        # 2) upload weight to garmin
        if self.upload_weights_to_GC(garmin, weights):
            with open(".last_sync.txt", "w") as F:
                F.write(datetime.datetime.now().isoformat())
        else:
            logger.error("Could not upload weights to Garmin Connect")

    def init_garmin(self) -> garminconnect.Garmin:
        try:
            garmin = garminconnect.Garmin()
            garmin.login(self.tokenstore)
        except (FileNotFoundError, GarthHTTPError, garminconnect.GarminConnectAuthenticationError):
            logger.debug("Generating tokenstore...")

            try:
                with self.SECRETS.open() as F:
                    secrets = yaml.safe_load(F)
            except Exception as err:
                logger.error(f"Could not load secrets.yaml")
                raise err

            email = secrets["garmin"]["email"]
            password = secrets["garmin"]["password"]
            try:
                garmin = garminconnect.Garmin(email, password)
                garmin.login()
                garmin.garth.dump(self.tokenstore)

            except (
                FileNotFoundError,
                GarthHTTPError,
                garminconnect.GarminConnectAuthenticationError,
                requests.exceptions.HTTPError,
            ) as err:
                logger.error("Could not login to Garmin Connect")
                raise err
        logging.debug("Logged into Garmin Connect")
        return garmin

    def upload_weights_to_GC(
        self, garmin: garminconnect.Garmin, measurements: list[Measurement]
    ) -> bool:
        """add weigh in, timestamp"""
        try:
            for measurement in measurements:
                weight = measurement.weight
                timestamp = measurement.datetime
                timestamp = datetime.datetime(
                    year=timestamp.year,
                    month=timestamp.month,
                    day=timestamp.day,
                    hour=timestamp.hour,
                    minute=timestamp.minute,
                    second=timestamp.second,
                    microsecond=123456,  # add fake microseconds for garminconnect
                )
                time_string = timestamp.isoformat()
                garmin.add_weigh_in(weight=weight, unitKey="kg", timestamp=time_string)
                logger.info(f"added {measurement} to Garmin Connect")
        except (
            garminconnect.GarminConnectConnectionError,
            garminconnect.GarminConnectAuthenticationError,
            garminconnect.GarminConnectTooManyRequestsError,
            requests.exceptions.HTTPError,
            GarthHTTPError,
        ) as err:
            logger.error(err)
            return False
        return True

    def init_withings(self) -> Any:
        withings_token_path = Path(self.tokenstore).joinpath("withings.json")
        if not withings_token_path.exists():
            logging.info("Running Withings authorization flow")
            auth_code = self.obtain_authorization_code()
            access_token, refresh_token = self.request_access_token(auth_code)
        else:
            with withings_token_path.open() as F:
                tokens = json.load(F)
            refresh_token = tokens["refresh_token"]
            # refresh token
            access_token, refresh_token = self.request_refresh(refresh_token)

        with withings_token_path.open("w") as F:
            json.dump({"refresh_token": refresh_token}, F)

        return access_token

    def obtain_authorization_code(self) -> Any:
        """get auth token from withings (OAuth2; step 1-3)"""
        scopes = ["user.metrics"]  # or user.info, user.activity
        redirect_uri = urllib.parse.urlunparse(self.parsed_withings_uri)
        state = str(
            hash(datetime.datetime.now())
        )  # something random to make sure we get the right response
        authorize_url = f"https://account.withings.com/oauth2_user/authorize2?response_type=code&client_id={self.withings_client_id}&scope={','.join(scopes)}&redirect_uri={redirect_uri}&state={state}"

        # 1) redirect user to authorization @withings.com
        logger.info(f"Redirecting to {authorize_url}")
        webbrowser.open(authorize_url)
        # 2) user authenticates and is redirected to withings_callback_uri
        # 3) flask retrieves auth code from url
        logger.debug("Waiting for authorization code")
        result = code_queue.get(timeout=60)
        assert result.get("state") == state, "State does not match"
        logger.debug("Got valid auth code")
        auth_code = result.get("code")
        assert auth_code is not None, "No auth code in response"
        return auth_code

    def request_access_token(self, auth_code: str) -> Any:
        # now: we use auth token to request an access_token and refresh_token
        payload = {
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "client_id": self.withings_client_id,
            "client_secret": self.withings_client_secret,
            "code": auth_code,
            "redirect_uri": urllib.parse.urlunparse(self.parsed_withings_uri),
        }
        logger.debug("Requesting access token...")
        result = requests.get(f"https://wbsapi.withings.net/v2/oauth2", params=payload).json()[
            "body"
        ]

        print(f"Got result: {result}")

        access_token = result["access_token"]
        refresh_token = result["refresh_token"]
        logger.debug("Got access token.")
        return access_token, refresh_token

    def request_refresh(self, refresh_token: str) -> tuple[str, str]:
        # use refresh token to get a new refresh token and access token
        logger.debug("Refreshing token...")
        payload = {
            "action": "requesttoken",
            "grant_type": "refresh_token",
            "client_id": self.withings_client_id,
            "client_secret": self.withings_client_secret,
            "refresh_token": refresh_token,
        }
        result = requests.get(f"https://wbsapi.withings.net/v2/oauth2", params=payload).json()[
            "body"
        ]
        access_token = result["access_token"]
        refresh_token = result["refresh_token"]
        logger.debug("Got new access token.")
        return access_token, refresh_token

    def get_weight_from_withings(
        self, access_token: str, last_sync: datetime.datetime
    ) -> list[Measurement]:
        headers = {"Authorization": "Bearer " + access_token}
        payload: dict[str, str | int] = {
            "action": "getmeas",
            "meastype": 1,
            "category": 1,
            "lastupdate": int(last_sync.timestamp()),
        }
        logger.debug("Requesting measurements from Withings...")
        result = requests.get(
            f"https://wbsapi.withings.net/v2/measure", headers=headers, params=payload
        ).json()

        logger.debug(f"Withings response: {result}")
        try:
            measurements = result["body"]["measuregrps"]
        except KeyError:
            logger.error(f"Could not retrieve measurements from Withings. Response:\n{result}")
            raise KeyError

        def to_measurement(m: dict) -> Measurement:
            date = datetime.datetime.fromtimestamp(m["date"])
            raw_measure = m["measures"][0]
            raw_value = raw_measure["value"]
            raw_unit = raw_measure["unit"]
            weight = raw_value * 10**raw_unit
            return Measurement(date, weight)

        logger.info(f"Retrieved {len(measurements)} measurements from Withings")
        return [to_measurement(m) for m in measurements]


if __name__ == "__main__":
    bridge = WithingsGCBridge()
    if UPDATE_INTERVAL > 0:
        while True:
            bridge.sync()
            time.sleep(UPDATE_INTERVAL)
    else:
        bridge = WithingsGCBridge()
        bridge.sync()
