import asyncio
import glob
import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Union
import string
import requests
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from py_yt import VideosSearch

from SHUKLAMUSIC import LOGGER
from SHUKLAMUSIC.utils.database import is_on_off
from SHUKLAMUSIC.utils.formatters import time_to_seconds

from config import YT_API_KEY, YTPROXY_URL as YTPROXY

logger = LOGGER(__name__)


def cookie_txt_file():
    try:
        folder_path = f"{os.getcwd()}/cookies"
        filename = f"{os.getcwd()}/cookies/logs.csv"
        txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
        if not txt_files:
            raise FileNotFoundError("No .txt files found in the specified folder.")
        cookie_txt_file = random.choice(txt_files)
        with open(filename, 'a') as file:
            file.write(f'Choosen File : {cookie_txt_file}\n')
        return f"""cookies/{str(cookie_txt_file).split("/")[-1]}"""
    except:
        return None


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        self.dl_stats = {
            "total_requests": 0,
            "okflix_downloads": 0,
            "cookie_downloads": 0,
            "existing_files": 0
        }

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        text = ""
        offset = None
        length = None

        for message in messages:
            if offset:
                break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url

        if offset is None:
            return None

        return text[offset: offset + length]

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link

        link = link.split("&")[0].split("?si=")[0]

        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]

            duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0

        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid=None):
        if videoid:
            link = self.base + link

        link = link.split("&")[0].split("?si=")[0]

        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["title"]

    async def duration(self, link: str, videoid=None):
        if videoid:
            link = self.base + link

        link = link.split("&")[0].split("?si=")[0]

        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["duration"]

    async def thumbnail(self, link: str, videoid=None):
        if videoid:
            link = self.base + link

        link = link.split("&")[0].split("?si=")[0]

        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["thumbnails"][0]["url"].split("?")[0]

    async def video(self, link: str, videoid=None):
        if videoid:
            link = self.base + link

        link = link.split("&")[0].split("?si=")[0]

        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "-g", "-f",
            "best[height<=?720][width<=?1280]",
            link,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        return 0, stderr.decode()

    async def track(self, link: str, videoid=None):
        if videoid:
            link = self.base + link

        link = link.split("&")[0].split("?si=")[0]

        results = VideosSearch(link, limit=1)
        result = (await results.next())["result"][0]

        return {
            "title": result["title"],
            "link": result["link"],
            "vidid": result["id"],
            "duration_min": result["duration"],
            "thumb": result["thumbnails"][0]["url"].split("?")[0],
        }, result["id"]

    async def download(
        self,
        link: str,
        mystic,
        video=None,
        videoid=None,
        songaudio=None,
        songvideo=None,
        format_id=None,
        title=None,
    ):
        if videoid:
            vid_id = link
            link = self.base + link

        def create_session():
            session = requests.Session()
            retries = Retry(total=3, backoff_factor=0.1)
            session.mount('http://', HTTPAdapter(max_retries=retries))
            session.mount('https://', HTTPAdapter(max_retries=retries))
            return session

        async def download_with_requests(url, filepath, headers=None):
            try:
                session = create_session()
                response = session.get(url, headers=headers, stream=True, timeout=60)
                response.raise_for_status()

                with open(filepath, 'wb') as file:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            file.write(chunk)

                return filepath
            except Exception as e:
                logger.error(f"Download failed: {e}")
                if os.path.exists(filepath):
                    os.remove(filepath)
                return None

        async def audio_dl(vid_id):
            headers = {"x-api-key": YT_API_KEY}
            filepath = f"downloads/{vid_id}.mp3"

            session = create_session()
            data = session.get(f"{YTPROXY}/info/{vid_id}", headers=headers).json()

            if data.get("status") == "success":
                return await download_with_requests(data["audio_url"], filepath, headers)

        async def video_dl(vid_id):
            headers = {"x-api-key": YT_API_KEY}
            filepath = f"downloads/{vid_id}.mp4"

            session = create_session()
            data = session.get(f"{YTPROXY}/info/{vid_id}", headers=headers).json()

            if data.get("status") == "success":
                return await download_with_requests(data["video_url"], filepath, headers)

        if video:
            return await video_dl(vid_id)
        return await audio_dl(vid_id)
