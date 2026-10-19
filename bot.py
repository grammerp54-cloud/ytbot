import os, re, json, html
import xml.etree.ElementTree as ET
import asyncio, aiohttp

TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_CHANNEL_ID = "1561737078855831582"
YT_HANDLE = "therobloxexecutorscripter"
STATE_FILE = "state.json"

HANDLE_URL = f"https://www.youtube.com/@{YT_HANDLE}"
NS = {"atom": "http://www.w3.org/2005/Atom",
      "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept-Language": "en-US,en;q=0.9",
           "Cookie": "CONSENT=YES+1; SOCS=CAI"}


def find_all(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            else:
                yield from find_all(v, key)
    elif isinstance(obj, list):
        for i in obj:
            yield from find_all(i, key)


async def send(session, content, embed):
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    async with session.post(url, json={"content": content, "embeds": [embed]},
                            headers={"Authorization": f"Bot {TOKEN}"}) as r:
        if r.status >= 300:
            print("Discord error", r.status, await r.text())
            return False
        return True


async def main():
    state = {"ids": [], "seeded": False}
    if os.path.exists(STATE_FILE):
        state = json.load(open(STATE_FILE))
    seen = set(state["ids"])

    async with aiohttp.ClientSession(headers=HEADERS) as s:
        # channel info
        async with s.get(HANDLE_URL) as r:
            page = await r.text()
        m = re.search(r'"channelId":"(UC[\w-]{22})"', page) or re.search(r'channel/(UC[\w-]{22})', page)
        yt_id = m.group(1) if m else None
        m = re.search(r'<meta property="og:image" content="([^"]+)"', page)
        icon = html.unescape(m.group(1)) if m else None
        m = re.search(r'<meta property="og:title" content="([^"]+)"', page)
        name = html.unescape(m.group(1)) if m else "The Roblox Executor Scripter"
        author = {"name": name, "url": HANDLE_URL}
        if icon:
            author["icon_url"] = icon

        items = []  # oldest first at the end

        # videos
        videos = []
        if yt_id:
            async with s.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_id}") as r:
                if r.status == 200:
                    root = ET.fromstring(await r.text())
                    for e in root.findall("atom:entry", NS):
                        vid = e.find("yt:videoId", NS).text
                        d = e.find("media:group", NS).find("media:description", NS)
                        desc = ((d.text or "") if d is not None else "").strip()
                        if len(desc) > 1000:
                            desc = desc[:1000] + "..."
                        url = f"https://www.youtube.com/watch?v={vid}"
                        videos.append((vid, f"🚨 **NEW VIDEO** 🚨\n{url}", {
                            "title": e.find("atom:title", NS).text, "url": url,
                            "description": desc or "No description.", "color": 0xFF0000,
                            "author": author, "image": {"url": f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"},
                            "timestamp": e.find("atom:published", NS).text,
                            **({"thumbnail": {"url": icon}} if icon else {}),
                            "footer": {"text": "YouTube"}}))
                else:
                    print("feed status", r.status)

        # community posts / polls (best effort)
        posts = []
        try:
            async with s.get(HANDLE_URL + "/posts") as r:
                page = await r.text()
            m = re.search(r"var ytInitialData = (\{.*?\});</script>", page, re.S)
            if m:
                data = json.loads(m.group(1))
                for p in find_all(data, "backstagePostRenderer"):
                    try:
                        pid = p["postId"]
                        text = "".join(x.get("text", "") for x in p.get("contentText", {}).get("runs", [])).strip()
                        att = p.get("backstageAttachment", {})
                        choices, image = [], None
                        if "pollRenderer" in att:
                            for c in att["pollRenderer"].get("choices", []):
                                choices.append("".join(x.get("text", "") for x in c.get("text", {}).get("runs", [])))
                        if "backstageImageRenderer" in att:
                            image = att["backstageImageRenderer"]["image"]["thumbnails"][-1]["url"]
                        poll = bool(choices)
                        text = text or ("New poll!" if poll else "New community post!")
                        if poll:
                            text += "\n\n" + "\n".join(f"**{i+1}.** {c}" for i, c in enumerate(choices))
                        url = f"https://www.youtube.com/post/{pid}"
                        emb = {"title": "📊 New Poll" if poll else "📢 New Community Post",
                               "url": url, "description": text[:4000], "color": 0x5865F2,
                               "author": author, "footer": {"text": "YouTube Community"}}
                        if image:
                            emb["image"] = {"url": image}
                        posts.append(("post:" + pid,
                                      ("📊 **NEW POLL**" if poll else "📢 **ANNOUNCEMENT**") + f"\n{url}", emb))
                    except Exception:
                        continue
        except Exception as e:
            print("posts error:", e)

        allitems = videos + posts
        if not state["seeded"]:
            if allitems:
                seen.update(i[0] for i in allitems)
                state["seeded"] = True
                print("First run: remembered", len(allitems), "existing items.")
        else:
            for iid, content, emb in reversed([i for i in allitems if i[0] not in seen]):
                if await send(s, content, emb):
                    seen.add(iid)

    state["ids"] = sorted(seen)
    json.dump(state, open(STATE_FILE, "w"))


asyncio.run(main())
