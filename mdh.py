import keyboard

import time
import yaml
import logging
import requests

from datetime import datetime, timedelta
from pypresence import Client
from pypresence.exceptions import DiscordError, ServerError

LOG_FORMAT = "[%(asctime)s][%(levelname)8s][%(funcName)20s:%(lineno)3s]: %(message)s"

DEFAUT_CONF = {
    "CLIENT_ID": None,
    "CLIENT_SECRET": None,
    "HOTKEYS": {},
    "__access_token": None,
    "__expire_token_date": None,
    "__refresh_token": None,
}


API_ENDPOINT = "https://discord.com/api/v8"
SCOPE = ["rpc", "rpc.voice.write", "rpc.voice.read"]
REDIRECT_URI = "http://localhost/"

discord_client: Client = None
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)

# =================================================================
#                           ACTIONS FUNCTIONS
# =================================================================


def toggle_mute(args):
    voice_status = discord_client.get_voice_settings()
    discord_client.set_voice_settings(mute=not voice_status["data"]["mute"])


def toggle_deaf(args):
    voice_status = discord_client.get_voice_settings()
    discord_client.set_voice_settings(deaf=not voice_status["data"]["deaf"])


ACTIONS = {"toggle_mute": toggle_mute, "toggle_deaf": toggle_deaf}




# =================================================================
#                           Code
# =================================================================

def get_config():
    try:
        with open("config.yml", "r") as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        if data["CLIENT_ID"] is None or data["CLIENT_SECRET"] is None:
            logging.fatal('Config missing, please specify "CLIENT_ID" and "CLIENT_SECRET"')
            exit(1)
        return data
    except FileNotFoundError:
        with open("config.yml", "w") as f:
            yaml.dump(DEFAUT_CONF, f)
        logging.fatal("Can't find config, generating defaut... Please fill the config file.")
        exit(1)


def save_config(conf):
    with open("config.yml", "w") as f:
        yaml.dump(conf, f)
    logging.debug("Config saved")


def init_discord(config):
    global discord_client
    discord_client = Client(config["CLIENT_ID"])
    while True:
        try:
            discord_client.start()
            token = get_discord_token(discord_client, config)
            discord_client.authenticate(token)
            logging.info("Discord connection OK")
            return discord_client
        except FileNotFoundError:
            logging.error("Fail to connect to Discord, retry in 10 sec...")
            time.sleep(10)
        except (ServerError, DiscordError) as error:
            logging.error(f"Discord Error... {error.args[0]}")
            time.sleep(30)
        except requests.exceptions.HTTPError as error:
            logging.error(f"Token error: {error.args[0]}")
            logging.error("Reset token and wait for 10 sec...")
            config["__access_token"] = None
            config["__expire_token_date"] = None
            config["__refresh_token"] = None
            save_config(config)
            time.sleep(10)


def get_grant_code(client, config):
    res = client.authorize(config.get("CLIENT_ID"), SCOPE)
    logging.debug("Authorize response: ")
    logging.debug(res)
    return res["data"]["code"]


def get_discord_token(client, config):
    token = config.get("__access_token")
    if token is None:
        logging.warning("No token, getting a new one...")
        logging.info("Getting grant code, a popup should apear in your Discord Client...")
        grant_code = get_grant_code(client, config)
        logging.info("...Grant code OK, exchange it to get Token...")
        response = exchange_grant_code(grant_code, config)
        config["__access_token"] = response["access_token"]
        expire_date = datetime.now() + timedelta(seconds=response["expires_in"])
        config["__expire_token_date"] = expire_date.isoformat()
        config["__refresh_token"] = response["refresh_token"]
        save_config(config)
        logging.info("...Done")
        return response["access_token"]
    else:
        if datetime.now() > datetime.fromisoformat(config["__expire_token_date"]):
            logging.info("Token expired, try refresh...")
            response = refresh_token(config)
            config["__access_token"] = response["access_token"]
            expire_date = datetime.now() + timedelta(seconds=response["expires_in"])
            config["__expire_token_date"] = expire_date.isoformat()
            config["__refresh_token"] = response["refresh_token"]
            save_config(config)
            logging.info("...Done")
            return response["access_token"]
        else:
            return token


def exchange_grant_code(grant_code, config):
    data = {
        "client_id": config.get("CLIENT_ID"),
        "client_secret": config.get("CLIENT_SECRET"),
        "grant_type": "authorization_code",
        "code": grant_code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post("%s/oauth2/token" % API_ENDPOINT, data=data, headers=headers)
    r.raise_for_status()
    return r.json()


def refresh_token(config):
    data = {
        "client_id": config.get("CLIENT_ID"),
        "client_secret": config.get("CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": config.get("__refresh_token"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post("%s/oauth2/token" % API_ENDPOINT, data=data, headers=headers)
    r.raise_for_status()
    return r.json()


def init_hotkeys(config):
    logging.info("Registering hotkeys...")
    for hotkey, value in config['HOTKEYS'].items():
        for action_id, args in value.items():
            action = ACTIONS.get(action_id)
            if action is not None:
                keyboard.add_hotkey(hotkey, action, args=[args])
                logging.info(f"...{hotkey} -> {action_id} Ok")
            else:
                logging.erro(f"Invalid hotkey action '{action_id}'")


config = get_config()
init_discord(config)
init_hotkeys(config)
keyboard.wait()
