# -*- coding: utf-8 -*-

import subprocess
import sys
import importlib.util
import time
import re
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

REQUIRED_PACKAGES = [
    ("requests", "requests"),
    ("beautifulsoup4", "bs4"),
    ("colorama", "colorama"),
    ("python-dateutil", "dateutil"),
]

def install_package(pkg):
    print(f"Ставлю {pkg}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", pkg])
        return True
    except:
        return False

def ensure_dependencies():
    for pkg_name, import_name in REQUIRED_PACKAGES:
        if importlib.util.find_spec(import_name) is None:
            print(f"Качаю недостающую либу {pkg_name}...")
            install_package(pkg_name)

ensure_dependencies()

import requests
from bs4 import BeautifulSoup
from colorama import init, Fore
from dateutil import parser

init(autoreset=True)

FALLOUTBUILDS_URL = "https://www.falloutbuilds.com/fo76/nuke-codes/"
NUKACRYPT_URL = "https://nukacrypt.com/"
NUKACRYPT_API_URL = "https://nukacrypt.com/api/codes"
REFRESH_INTERVAL = 60
CACHE_FILE = "nuke_cache.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

LANGUAGES = {
    "ru": {
        "title": "FALLOUT 76 – КОДЫ ЯДЕРНЫХ ШАХТ",
        "creator": "Создатель: Hate 6.0",
        "updated": "Обновлено:",
        "never": "Никогда",
        "next_update": "Обнова через",
        "sec": "сек.",
        "silo": "Шахта",
        "code": "Код",
        "expires": "Сгорает (UTC)",
        "remains": "Осталось",
        "seconds": "Секунд",
        "source": "Источник",
        "press_exit": "Выход по Ctrl+C",
        "cache_wait": "Кэша нет, жду данные...",
        "parsing_fb": "Чатюсь с falloutbuilds...",
        "parsing_nk": "Чатюсь с nukacrypt...",
        "success": "Всё успешно сграбблено.",
        "use_cache": "Беру из кэша.",
        "error_fetch": "Не удалось доступиться никуда.",
        "error_save": "Траблик с кэшем:",
        "error_parse": "Ошибка разбора",
        "unknown": "Хз",
        "d": "д", "h": "ч", "m": "м",
        "exit_graceful": "Пока!",
        "exit_error": "Упали с ошибкой:"
    },
    "en": {
        "title": "FALLOUT 76 – NUKE CODES",
        "creator": "Creator: Hate 6.0",
        "updated": "Updated:",
        "never": "Never",
        "next_update": "Next update in",
        "sec": "sec.",
        "silo": "Silo",
        "code": "Code",
        "expires": "Expires (UTC)",
        "remains": "Remaining",
        "seconds": "Seconds",
        "source": "Source",
        "press_exit": "Press Ctrl+C to exit",
        "cache_wait": "No cache, waiting for data...",
        "parsing_fb": "Parsing falloutbuilds...",
        "parsing_nk": "Parsing nukacrypt...",
        "success": "Got data successfully.",
        "use_cache": "Using cache.",
        "error_fetch": "Failed to fetch from anywhere.",
        "error_save": "Cache error:",
        "error_parse": "Parse error at",
        "unknown": "Unknown",
        "d": "d", "h": "h", "m": "m",
        "exit_graceful": "Exited.",
        "exit_error": "Exited with error:"
    }
}

class NukeTracker:
    def __init__(self, lang="ru"):
        self.lang = lang
        self.t = LANGUAGES[self.lang]
        
        self.sources = {
            "falloutbuilds": {"codes": {}, "expires": None},
            "nukacrypt": {"codes": {}, "expires": None},
        }
        self.codes = {
            "Alpha": {"code": "N/A", "expires": None, "source": ""},
            "Bravo": {"code": "N/A", "expires": None, "source": ""},
            "Charlie": {"code": "N/A", "expires": None, "source": ""},
        }
        self.last_update = None
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.running = True

    def _get_next_thursday_reset(self):
        now = datetime.now(timezone.utc)
        days_until_thursday = (3 - now.weekday()) % 7
        if days_until_thursday == 0 and now.hour >= 0:
            days_until_thursday = 7
        return (now + timedelta(days=days_until_thursday)).replace(hour=0, minute=0, second=0, microsecond=0)

    def _parse_expiration_date(self, date_str):
        try:
            exp_date = parser.parse(date_str, fuzzy=True)
            if exp_date.tzinfo is None:
                exp_date = exp_date.replace(tzinfo=timezone.utc)
            if exp_date <= datetime.now(timezone.utc):
                return self._get_next_thursday_reset()
            return exp_date
        except:
            return self._get_next_thursday_reset()

    def _load_cache(self):
        try:
            cache_path = Path(CACHE_FILE)
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for site in self.codes:
                    if site in data.get("codes", {}):
                        self.codes[site]["code"] = data["codes"][site].get("code", "N/A")
                        exp_str = data["codes"][site].get("expires")
                        self.codes[site]["expires"] = datetime.fromisoformat(exp_str).replace(tzinfo=timezone.utc) if exp_str else None
                        self.codes[site]["source"] = data["codes"][site].get("source", "cache")
                self.last_update = datetime.fromisoformat(data["last_update"]).replace(tzinfo=timezone.utc) if data.get("last_update") else None
                return True
            return False
        except:
            return False

    def _save_cache(self):
        try:
            data = {
                "codes": {site: {"code": self.codes[site]["code"],
                                 "expires": self.codes[site]["expires"].isoformat() if self.codes[site]["expires"] else None,
                                 "source": self.codes[site]["source"]}
                          for site in self.codes},
                "last_update": self.last_update.isoformat() if self.last_update else None
            }
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"{Fore.RED}{self.t['error_save']} {e}")

    def _fetch_falloutbuilds(self):
        try:
            resp = self.session.get(FALLOUTBUILDS_URL, timeout=15)
            if resp.status_code != 200:
                return False
            soup = BeautifulSoup(resp.text, 'html.parser')
            card = soup.find('div', class_='card-terminal')
            
            self.sources["falloutbuilds"]["codes"] = {}
            self.sources["falloutbuilds"]["expires"] = None

            if card:
                code_container = card.find('div', class_='d-flex')
                if code_container:
                    for site in ["Alpha", "Bravo", "Charlie"]:
                        small = code_container.find('small', string=re.compile(re.escape(site), re.IGNORECASE))
                        if not small or not small.parent:
                            continue
                        next_elem = small.next_sibling
                        while next_elem and isinstance(next_elem, str) and not next_elem.strip():
                            next_elem = next_elem.next_sibling
                        if next_elem and next_elem.name == 'br':
                            next_elem = next_elem.next_sibling
                            while next_elem and isinstance(next_elem, str) and not next_elem.strip():
                                next_elem = next_elem.next_sibling
                        if next_elem and isinstance(next_elem, str):
                            code = next_elem.strip().replace(' ', '')
                            if len(code) == 8 and code.isdigit():
                                self.sources["falloutbuilds"]["codes"][site] = code

                date_match = re.search(r'Valid to\s+([^\n]+)', card.get_text(), re.IGNORECASE)
                if date_match:
                    self.sources["falloutbuilds"]["expires"] = self._parse_expiration_date(date_match.group(1).strip())

            if not self.sources["falloutbuilds"]["codes"]:
                text = soup.get_text()
                for site in ["Alpha", "Bravo", "Charlie"]:
                    match = re.search(rf'{site}.*?(\b\d{{8}}\b)', text, re.IGNORECASE | re.DOTALL)
                    if match:
                        self.sources["falloutbuilds"]["codes"][site] = match.group(1)

            if not self.sources["falloutbuilds"]["expires"]:
                self.sources["falloutbuilds"]["expires"] = self._get_next_thursday_reset()

            return bool(self.sources["falloutbuilds"]["codes"])
        except Exception as e:
            print(f"{Fore.YELLOW}{self.t['error_parse']} fb: {e}")
            return False

    def _fetch_nukacrypt(self):
        try:
            codes = {}
            try:
                api_resp = self.session.get(NUKACRYPT_API_URL, timeout=10)
                if api_resp.status_code == 200:
                    data = api_resp.json()
                    for site in ["Alpha", "Bravo", "Charlie"]:
                        key = site.lower()
                        if key in data and data[key]:
                            codes[site] = str(data[key]).strip()
            except:
                pass

            page_resp = self.session.get(NUKACRYPT_URL, timeout=10)
            if page_resp.status_code == 200:
                html = page_resp.text
                if not codes:
                    for site in ["Alpha", "Bravo", "Charlie"]:
                        match = re.search(rf'{site}.*?(\b\d{{8}}\b)', html, re.IGNORECASE | re.DOTALL)
                        if match:
                            codes[site] = match.group(1)

                reset_match = re.search(r'Resets\s+in:\s*(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?', html, re.IGNORECASE)
                if reset_match:
                    days = int(reset_match.group(1) or 0)
                    hours = int(reset_match.group(2) or 0)
                    mins = int(reset_match.group(3) or 0)
                    self.sources["nukacrypt"]["expires"] = datetime.now(timezone.utc) + timedelta(days=days, hours=hours, minutes=mins)

            if not self.sources["nukacrypt"]["expires"]:
                self.sources["nukacrypt"]["expires"] = self._get_next_thursday_reset()

            self.sources["nukacrypt"]["codes"] = codes
            return bool(codes)
        except Exception as e:
            print(f"{Fore.RED}{self.t['error_parse']} nk: {e}")
            return False

    def _merge_data(self):
        for site in self.codes:
            self.codes[site]["code"] = "N/A"
            self.codes[site]["expires"] = None
            self.codes[site]["source"] = ""

        fb_codes = self.sources["falloutbuilds"]["codes"]
        nk_codes = self.sources["nukacrypt"]["codes"]
        fb_exp = self.sources["falloutbuilds"]["expires"]
        nk_exp = self.sources["nukacrypt"]["expires"]

        if not fb_codes and not nk_codes:
            return False

        for site in ["Alpha", "Bravo", "Charlie"]:
            fb_code = fb_codes.get(site, "")
            nk_code = nk_codes.get(site, "")

            if fb_code and nk_code and fb_code == nk_code:
                self.codes[site]["code"] = fb_code
                self.codes[site]["source"] = "both"
            elif fb_code and not nk_code:
                self.codes[site]["code"] = fb_code
                self.codes[site]["source"] = "fb"
            elif nk_code and not fb_code:
                self.codes[site]["code"] = nk_code
                self.codes[site]["source"] = "nk"
            elif fb_code and nk_code and fb_code != nk_code:
                self.codes[site]["code"] = fb_code
                self.codes[site]["source"] = f"fb (nk:{nk_code})"

        expires_date = nk_exp or fb_exp or self._get_next_thursday_reset()
        for site in self.codes:
            self.codes[site]["expires"] = expires_date

        return any(c["code"] != "N/A" for c in self.codes.values())

    def _fetch_data(self):
        print(f"{Fore.CYAN}{self.t['parsing_fb']}")
        self._fetch_falloutbuilds()
        print(f"{Fore.CYAN}{self.t['parsing_nk']}")
        self._fetch_nukacrypt()

        if self._merge_data():
            print(f"{Fore.GREEN}{self.t['success']}")
            return True
        else:
            if self._load_cache():
                print(f"{Fore.YELLOW}{self.t['use_cache']}")
                return True
            return False

    def _get_time_info(self, expires):
        if expires is None:
            return self.t['unknown'], 0
        delta = expires - datetime.now(timezone.utc)
        total_seconds = int(delta.total_seconds())
        if total_seconds <= 0:
            return f"0{self.t['d']} 00{self.t['h']} 00{self.t['m']}", 0
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        mins, _ = divmod(rem, 60)
        return f"{days}{self.t['d']} {hours:02d}{self.t['h']} {mins:02d}{self.t['m']}", total_seconds

    def display(self):
        import os
        os.system('cls' if os.name == 'nt' else 'clear')

        print(f"{Fore.MAGENTA}{'='*85}")
        print(f"{Fore.CYAN}         {self.t['title']} | {self.t['creator']}")
        print(f"{Fore.MAGENTA}{'='*85}")

        update_str = self.last_update.strftime('%Y-%m-%d %H:%M:%S UTC') if self.last_update else self.t['never']
        print(f"{Fore.WHITE}{self.t['updated']} {update_str}")
        print(f"{Fore.WHITE}{self.t['next_update']} {REFRESH_INTERVAL} {self.t['sec']}")
        print("")
        print(f"{Fore.YELLOW}{self.t['silo']:<10} {self.t['code']:<12} {self.t['expires']:<22} {self.t['remains']:<18} {self.t['seconds']:<12} {self.t['source']}")
        print(f"{Fore.YELLOW}{'-'*85}")

        for site in ["Alpha", "Bravo", "Charlie"]:
            info = self.codes[site]
            code = info["code"]
            expires = info["expires"]
            source = info["source"]

            exp_str = expires.strftime('%Y-%m-%d %H:%M') if expires else self.t['unknown']
            time_str, seconds = self._get_time_info(expires)

            code_color = Fore.GREEN if code != "N/A" else Fore.RED
            seconds_str = f"{seconds:,}" if seconds > 0 else "0"

            print(f"{Fore.WHITE}{site:<10} {code_color}{code:<12} {Fore.WHITE}{exp_str:<22} {time_str:<18} {seconds_str:>12} {source}")

        print(f"{Fore.MAGENTA}{'='*85}")
        print(f"{Fore.WHITE}{self.t['press_exit']}")

    def run(self):
        if not self._load_cache():
            print(f"{Fore.YELLOW}{self.t['cache_wait']}")

        while self.running:
            if self._fetch_data():
                self.last_update = datetime.now(timezone.utc)
                self._save_cache()
            else:
                print(f"{Fore.RED}{self.t['error_fetch']}")

            self.display()

            for _ in range(REFRESH_INTERVAL):
                if not self.running:
                    break
                time.sleep(1)

    def stop(self):
        self.running = False
        self.session.close()

def main():
    print("=============================")
    print(" Выберите язык / Language:   ")
    print(" 1 - Русский (RU)            ")
    print(" 2 - English (EN)            ")
    print("=============================")
    
    choice = input("> ").strip()
    lang = "en" if choice == "2" else "ru"
    
    tracker = NukeTracker(lang=lang)
    try:
        tracker.run()
    except KeyboardInterrupt:
        tracker.stop()
        print(f"\n{Fore.YELLOW}{tracker.t['exit_graceful']}")
        sys.exit(0)
    except Exception as e:
        tracker.stop()
        print(f"\n{Fore.RED}{tracker.t['exit_error']} {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()