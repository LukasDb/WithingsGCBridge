import time
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

import withings_api
import os

UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 0))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wt_gc_bridge")

app = Flask(__name__)
code_queue = queue.Queue()


@dataclass
class Measurement:
    datetime: datetime.datetime
    weight: float


class WithingsGCBridge:
    SECRETS = Path("secrets.yaml")
    tokenstore = ".tokenstore"
    withings_callback_uri: str = "http://127.0.0.1:5000"
    garmin: garminconnect.Garmin

    def __init__(self):
        self.garmin = self.init_garmin()
        self.withings_access_token = self.init_withings()

    def sync(self):
        try:
            with open(".last_sync.txt", "r") as F:
                self.last_sync = datetime.datetime.fromisoformat(F.read())
        except Exception:
            self.last_sync = datetime.datetime.now() - datetime.timedelta(days=7)
        # 1) get weight with timestamp from withings
        weights = self.get_weight_from_withings()

        # 2) upload weight to garmin
        self.upload_weights_to_GC(weights)

        with open(".last_sync.txt", "w") as F:
            F.write(datetime.datetime.now().isoformat())

    def init_garmin(self):
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

        return garmin

    def upload_weights_to_GC(self, measurements: list[Measurement]):
        """add weigh in, timestamp"""
        try:
            for measurement in measurements:
                weight = measurement.weight
                timestamp = measurement.datetime
                self.garmin.add_weigh_in(
                    weight=weight, unitKey="kg", timestamp=timestamp.isoformat()
                )
                logger.info(f"added {measurement} to Garmin Connect")
        except (
            garminconnect.GarminConnectConnectionError,
            garminconnect.GarminConnectAuthenticationError,
            garminconnect.GarminConnectTooManyRequestsError,
            requests.exceptions.HTTPError,
            GarthHTTPError,
        ) as err:
            logger.error(err)

    def init_withings(self):
        try:
            with self.SECRETS.open() as F:
                secrets = yaml.safe_load(F)
        except Exception as err:
            logger.error(f"Could not load secrets.yaml")
            raise err

        try:
            client_id = secrets["withings"]["client_id"]
            secret = secrets["withings"]["secret"]
        except KeyError as err:
            logger.error(f"Could not load secrets.yaml")
            raise err

        if "callback_uri" in secrets["withings"]:
            self.withings_callback_uri = secrets["withings"]["callback_uri"]

        parsed_uri = urllib.parse.urlparse(self.withings_callback_uri)

        auth = withings_api.WithingsAuth(
            client_id=client_id,
            consumer_secret=secret,
            callback_uri=urllib.parse.urlunparse(parsed_uri),
            mode="demo",
            scope=(
                withings_api.AuthScope.USER_METRICS,
                withings_api.AuthScope.USER_INFO,
                withings_api.AuthScope.USER_ACTIVITY,
            ),
        )

        try:
            with Path(self.tokenstore).joinpath("withings.json").open("r") as F:
                access_token = json.load(F)["access_token"]

        except Exception:
            access_token = self.register_withings(parsed_uri, auth)
        return access_token

    def register_withings(
        self, parsed_uri: urllib.parse.ParseResult, auth: withings_api.WithingsAuth
    ):
        # start flask
        threading.Thread(
            target=lambda: app.run(debug=False, host=parsed_uri.hostname, port=parsed_uri.port),
            daemon=True,
        ).start()

        authorize_url = auth.get_authorize_url()

        webbrowser.open(authorize_url)

        auth_code = code_queue.get()
        credentials = auth.get_credentials(auth_code)

        with Path(self.tokenstore).joinpath("withings.json").open("w") as F:
            json.dump({"access_token": credentials.access_token}, F)

        return credentials.access_token

    def get_weight_from_withings(self) -> list[Measurement]:
        headers = {"Authorization": "Bearer " + self.withings_access_token}
        payload = {
            "action": "getmeas",
            "meastype": 1,
            "category": 1,
            "lastupdate": int(self.last_sync.timestamp()),
        }

        # List devices of returned user
        result = requests.get(
            f"https://wbsapi.withings.net/v2/measure", headers=headers, params=payload
        ).json()

        logger.debug(f"Withings response: {result}")
        measurements = result["body"]["measuregrps"]

        def to_measurement(m):
            date = datetime.datetime.fromtimestamp(m["date"])
            raw_measure = m["measures"][0]
            raw_value = raw_measure["value"]
            raw_unit = raw_measure["unit"]
            weight = raw_value * 10**raw_unit
            return Measurement(date, weight)

        logger.info(f"Retrieved {len(measurements)} measurements from Withings")
        return [to_measurement(m) for m in measurements]

    @app.route("/")
    def get_token():
        code = request.args.get("code")
        code_queue.put(code)
        return "<p>Success!</p>"


if __name__ == "__main__":
    bridge = WithingsGCBridge()
    if UPDATE_INTERVAL > 0:
        while True:
            bridge.sync()
            time.sleep(UPDATE_INTERVAL)
    else:
        bridge.sync()
