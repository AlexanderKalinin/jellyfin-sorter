#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import time
import json
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

# ================== КОНФИГ ==================

# Jellyfin
JELLYFIN_SERVER = "http://192.168.1.6:8096"
JELLYFIN_API_KEY = "acf741a88735410dbfecb9970d518655"

# Kinopoisk.dev (основной источник)
KINOPOISK_DEV_API_KEY = "QAZWJHA-ADC4FDE-Q9R72P1-E6VVJF8"
KINOPOISK_DEV_BASE = "https://api.kinopoisk.dev"

# Необязательный запасной ключ kinopoiskapiunofficial.tech
# здесь пока не используем напрямую, но оставляем для расширения
KINOPOISK_UNOFFICIAL_API_KEY = "c63adf87-8d20-48f7-953c-71abefc3850a"
KINOPOISK_UNOFFICIAL_BASE = "https://kinopoiskapiunofficial.tech"

# Пути для медиатеки
NFO_DIRS = [
    "/mnt/RAID/media/main/movies",
    "/mnt/RAID/media/main/shows",
]

# Лимиты
KINOPOISK_TIMEOUT = 10
JELLYFIN_TIMEOUT = 10

# ================== ЛОГИ ==================

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)

log = logging.getLogger("jellyfin-people-sync")

# ================== УТИЛИТЫ ==================


def safe_request(method, url, **kwargs):
    """
    Обёртка над requests, чтобы не заваливать скрипт при сети/таймаутах.
    """
    try:
        resp = requests.request(method, url, timeout=kwargs.pop("timeout", 10), **kwargs)
        return resp
    except Exception as e:
        log.warning(f"[HTTP ERROR] {url}: {e}")
        return None


def is_empty(s):
    return s is None or str(s).strip() == ""


# ================== СКАН NFO ==================


def scan_nfo_for_persons(dirs):
    """
    Сканируем NFO-файлы, собираем имена актёров + список файлов, где они встречаются.
    Возвращаем: dict[str, set[str]]: имя -> множество путей NFO.
    """
    persons = {}
    total_persons = 0

    log.info("Сканирую NFO...")
    for base in dirs:
        if not os.path.isdir(base):
            continue
        log.info(f"  Сканирую NFO в: {base}")
        for root_dir, _, files in os.walk(base):
            for fname in files:
                if not fname.lower().endswith(".nfo"):
                    continue
                full_path = os.path.join(root_dir, fname)
                try:
                    tree = ET.parse(full_path)
                    root = tree.getroot()
                except Exception:
                    # бывает кривая разметка / не-XML
                    continue

                # Kodi-style: <actor><name>Имя</name>...</actor>
                for actor in root.findall(".//actor"):
                    name_el = actor.find("name")
                    if name_el is None or is_empty(name_el.text):
                        continue
                    name = name_el.text.strip()
                    if not name:
                        continue
                    total_persons += 1
                    if name not in persons:
                        persons[name] = set()
                    persons[name].add(full_path)

    log.info(f"Уникальных персон по всем NFO: {len(persons)} (всего вхождений: {total_persons})")
    return persons


# ================== KINOPOISK ==================


def kinopoisk_dev_search_person(name_ru):
    """
    Поиск персоны по имени (русскому) через api.kinopoisk.dev /v1.4/person.
    Возвращает dict с ключами:
        kp_id, name_ru, name_en, photo_url, description
    или None, если совсем ничего.
    """
    headers = {
        "X-API-KEY": KINOPOISK_DEV_API_KEY,
        "accept": "application/json",
    }
    params = {
        "page": 1,
        "limit": 5,
        "name": name_ru,
    }
    url = f"{KINOPOISK_DEV_BASE}/v1.4/person"

    resp = safe_request("GET", url, headers=headers, params=params, timeout=KINOPOISK_TIMEOUT)
    if resp is None:
        log.warning(f"[KINOPOISK] запрос провалился для '{name_ru}'")
        return None

    if resp.status_code != 200:
        log.warning(f"[KINOPOISK] HTTP {resp.status_code} для '{name_ru}': {resp.text[:200]}")
        return None

    try:
        data = resp.json()
    except Exception as e:
        log.warning(f"[KINOPOISK] JSON ошибка для '{name_ru}': {e}")
        return None

    docs = data.get("docs") or data.get("items") or []
    if not docs:
        log.info(f"[KINOPOISK] нет результатов для '{name_ru}'")
        return None

    # Находим лучший матч:
    # 1) точное совпадение name
    # 2) иначе первый документ
    best = None
    lowered = name_ru.lower()
    for d in docs:
        n = (d.get("name") or "").lower()
        if n == lowered:
            best = d
            break
    if best is None:
        best = docs[0]

    kp_id = best.get("id") or best.get("kpId") or best.get("kinopoiskId")
    name_ru_res = best.get("name") or best.get("nameRu")
    name_en_res = best.get("enName") or best.get("nameEn")
    photo_url = best.get("photo") or best.get("posterUrl")
    description = best.get("description") or best.get("bio") or ""

    if kp_id is None:
        log.warning(f"[KINOPOISK] нет ID в ответе для '{name_ru}', пропускаю")
        return None

    return {
        "kp_id": kp_id,
        "name_ru": name_ru_res or name_ru,
        "name_en": name_en_res,
        "photo_url": photo_url,
        "description": description,
    }


# ================== РАБОТА С NFO (обновление актёра) ==================


def update_actor_in_nfo(nfo_path, person_name, kp_info):
    """
    В указанном NFO находим <actor><name>person_name</name>...</actor>
    и прописываем:
        <kp_id>...</kp_id> (кастомный тег)
        <kp_name_en>...</kp_name_en> (кастомный тег)
        <thumb>...</thumb> (если пусто и есть photo_url)
    """
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()
    except Exception:
        return False

    changed = False

    for actor in root.findall(".//actor"):
        name_el = actor.find("name")
        if name_el is None or is_empty(name_el.text):
            continue
        if name_el.text.strip() != person_name:
            continue

        # kp_id
        kp_id_el = actor.find("kp_id")
        if kp_id_el is None:
            kp_id_el = ET.SubElement(actor, "kp_id")
        old_kp_id = kp_id_el.text or ""
        new_kp_id = str(kp_info["kp_id"])
        if old_kp_id != new_kp_id:
            kp_id_el.text = new_kp_id
            changed = True

        # English name
        if kp_info.get("name_en"):
            kp_en_el = actor.find("kp_name_en")
            if kp_en_el is None:
                kp_en_el = ET.SubElement(actor, "kp_name_en")
            old_en = kp_en_el.text or ""
            if old_en != kp_info["name_en"]:
                kp_en_el.text = kp_info["name_en"]
                changed = True

        # thumb (avatar)
        if kp_info.get("photo_url"):
            thumb_el = actor.find("thumb")
            if thumb_el is None:
                thumb_el = ET.SubElement(actor, "thumb")
            old_thumb = thumb_el.text or ""
            if is_empty(old_thumb):
                thumb_el.text = kp_info["photo_url"]
                changed = True

    if changed:
        # аккуратно сохраняем с той же кодировкой; по умолчанию utf-8
        tree.write(nfo_path, encoding="utf-8", xml_declaration=True)
    return changed


def update_person_in_all_nfo(person_name, nfo_paths, kp_info):
    """
    Обновляем все NFO-файлы, где встречается указанный актёр.
    """
    updated = 0
    for path in nfo_paths:
        if update_actor_in_nfo(path, person_name, kp_info):
            updated += 1
    if updated > 0:
        log.info(f"[NFO] Обновлён актёр '{person_name}' в {updated} NFO-файлах")
    return updated


# ================== JELLYFIN ==================


def jellyfin_get_person_by_name(name):
    """
    Получаем объект Person из Jellyfin по имени.
    Используется эндпоинт /Persons/{name}
    """
    url_name = quote(name)
    url = f"{JELLYFIN_SERVER}/Persons/{url_name}"
    params = {"api_key": JELLYFIN_API_KEY}
    resp = safe_request("GET", url, params=params, timeout=JELLYFIN_TIMEOUT)
    if resp is None or resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    return data


def jellyfin_download_person_image(item_id, image_url):
    """
    Запрашиваем у Jellyfin скачать внешнее изображение как Primary.
    /Items/{id}/RemoteImages/Download?Type=Primary&ImageUrl=...
    """
    url = f"{JELLYFIN_SERVER}/Items/{item_id}/RemoteImages/Download"
    params = {
        "api_key": JELLYFIN_API_KEY,
        "Type": "Primary",
        "ImageUrl": image_url,
    }
    resp = safe_request("POST", url, params=params, timeout=JELLYFIN_TIMEOUT)
    if resp is None:
        return False
    if resp.status_code not in (200, 204):
        log.warning(f"[JF] Ошибка загрузки изображения для Item={item_id}: HTTP {resp.status_code} {resp.text[:200]}")
        return False
    return True


def jellyfin_update_person_overview(item_id, overview):
    """
    Обновляем Overview (био) для персоны.
    POST /Items/{id}
    """
    url = f"{JELLYFIN_SERVER}/Items/{item_id}"
    params = {"api_key": JELLYFIN_API_KEY}
    payload = {
        "Id": item_id,
        "Overview": overview,
    }
    headers = {"Content-Type": "application/json"}
    resp = safe_request("POST", url, params=params, headers=headers, data=json.dumps(payload), timeout=JELLYFIN_TIMEOUT)
    if resp is None:
        return False
    if resp.status_code not in (200, 204):
        log.warning(f"[JF] Ошибка обновления Overview для Item={item_id}: HTTP {resp.status_code} {resp.text[:200]}")
        return False
    return True


def jellyfin_enrich_person(person_name, kp_info):
    """
    Для актёра:
      - Находим Person в Jellyfin.
      - Если нет PrimaryImageTag и есть фото из Кинопоиска -> качаем.
      - Если пустой Overview и есть описание -> обновляем.
    """
    jf_person = jellyfin_get_person_by_name(person_name)
    if jf_person is None:
        log.info(f"[JF] Person '{person_name}' пока не найден (создастся при следующем скане библиотеки)")
        return

    item_id = jf_person.get("Id")
    if not item_id:
        return

    primary_tag = jf_person.get("PrimaryImageTag")
    overview = jf_person.get("Overview") or ""

    # аватар
    if is_empty(primary_tag) and kp_info.get("photo_url"):
        if jellyfin_download_person_image(item_id, kp_info["photo_url"]):
            log.info(f"[JF] Задан Primary image для '{person_name}' из Кинопоиска")

    # био
    if is_empty(overview) and kp_info.get("description"):
        if jellyfin_update_person_overview(item_id, kp_info["description"]):
            log.info(f"[JF] Обновлено био (Overview) для '{person_name}'")


# ================== ОСНОВНОЙ ЦИКЛ ==================


def main():
    persons_map = scan_nfo_for_persons(NFO_DIRS)
    total_unique = len(persons_map)
    if total_unique == 0:
        log.info("Персон не найдено, делать нечего.")
        return

    processed = 0
    kino_cache = {}

    for name, nfo_paths in sorted(persons_map.items(), key=lambda x: x[0].lower()):
        processed += 1
        log.info(f"[KINO] ({processed}/{total_unique}) Обрабатываю: {name}")

        if name in kino_cache:
            kp_info = kino_cache[name]
        else:
            kp_info = kinopoisk_dev_search_person(name)
            kino_cache[name] = kp_info

        if kp_info is None:
            log.info(f"[KINOPOISK] '{name}' -> совпадений нет, пропуск")
            continue

        log.info(
            f"[KINOPOISK] '{name}' -> kp_id={kp_info['kp_id']}, "
            f"ru='{kp_info.get('name_ru')}', en='{kp_info.get('name_en')}'"
        )

        # Обновляем NFO
        update_person_in_all_nfo(name, nfo_paths, kp_info)

        # Обновляем Jellyfin (аватары + био)
        jellyfin_enrich_person(name, kp_info)

        # Чуть притормозим, чтобы не долбить API
        time.sleep(0.2)

    log.info(f"Всего персон в NFO: {total_unique}")
    log.info(f"Обработано за запуск: {processed}")


if __name__ == "__main__":
    main()
