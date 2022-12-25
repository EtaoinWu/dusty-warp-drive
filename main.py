import asyncio
import json
import datetime
import dateutil
import re
import math

# read config file
with open("config.json") as f:
    config = json.load(f)


def human_readable_time(td: datetime.timedelta) -> str:
    seconds = math.floor(td.total_seconds())
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days > 0:
        return f"{days} days, {hours % 24} hours, {minutes % 60} minutes"
    elif hours > 0:
        return f"{hours} hours, {minutes % 60} minutes"
    elif minutes > 0:
        return f"{minutes} minutes"
    else:
        return f"{seconds} s"


def escape_space(text: str) -> str:
    # escape spaces into \s
    return text.strip().replace(" ", "\\s")


def unescape_space(text: str) -> str:
    # unescape spaces from \s
    return text.strip().replace("\\s", " ")


class ClientState:
    def __init__(self):
        self.away = False
        self.last_seen = datetime.datetime.now()
        self.away_message = "sleep"
        self.status = "online"

    def update(self, away: bool, away_message: str) -> str:
        away_message = unescape_space(away_message)
        if away != self.away:
            print(f"away: {away} {away_message}")
        if away_message != self.away_message:
            print(f"away_message: {away_message}")
        self.away_message = away_message
        self.away = away
        if not away:
            self.last_seen = datetime.datetime.now()
        # parse the away message format: <text> {<human readable time>}
        if away:
            match = re.match(r"^(.*?)(\{.*\})?$", away_message)
            if match is None:
                return ""
            text = match.group(1).strip()
            self.status = f"{text} \u007baway for {human_readable_time(datetime.datetime.now() - self.last_seen)}\u007d"
            return self.status
        else:
            return ""


async def client():
    state = ClientState()
    while True:
        reader, writer = await asyncio.open_connection(config["host"], config["port"])

        async def query(q: str, lines: int = 1) -> list[str]:
            writer.write(f"{q}\n".encode("utf-8"))
            await writer.drain()
            response = []
            for _ in range(lines):
                response.append((await reader.readline()).decode("utf-8").strip())
            return response

        # skip the first 4 lines
        for _ in range(4):
            await reader.readline()

        # authenticate with api key
        result = await query(f"auth apikey={config['api_key']}")
        if result[0] != "error id=0 msg=ok":
            print("authentication failed")
            break

        while True:
            await asyncio.sleep(5)
            # retry if the connection is closed
            if writer.is_closing():
                break
            if reader.at_eof():
                break

            # query whoami
            whoami = await query("whoami", 2)
            if whoami[1] != "error id=0 msg=ok":
                print(f"whoami failed: {whoami[1]}")
                break
            # parse clid=<client id> cid=<channel id>
            match = re.match(r"clid=(\d+) cid=(\d+)", whoami[0])
            if match is None:
                continue
            clid = int(match.group(1))
            print(f"clid: {clid}")

            # query the away status and away message
            away = await query(
                f"clientvariable clid={clid} client_away client_away_message", 2
            )
            if away[1] != "error id=0 msg=ok":
                print(f"clientvariable failed: {away[1]}")
                break
            # parse response: clid=<clid> client_away=<away> client_away_message=<away_text>
            match = re.match(
                r"clid=\d+ client_away=(\d) client_away_message=?(.*)", away[0]
            )
            if match is None:
                continue
            away = bool(int(match.group(1)))
            away_message = match.group(2)

            # update the state
            status = state.update(away, away_message)
            print(f"calculated status: {status}")
            if status != "":
                # set status
                update = await query(
                    f"clientupdate client_away_message={escape_space(status)}"
                )
                if update[0] != "error id=0 msg=ok":
                    print(f"clientupdate failed: {update[0]}")
                    break


asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(client())
