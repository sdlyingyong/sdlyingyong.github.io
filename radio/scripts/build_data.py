#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radio Browser -> 天球星图数据分片

产出两个文件（放 radio/data/）：
  core.json  列式整数数组：坐标 + 国家/曲风/语种/地区/码率索引，首屏就用它画点
  meta.json  台名 + 流地址（体积大头，后台加载，到了再补卡片文字）

用法：
  python3 build_data.py                 # 联网抓全量
  python3 build_data.py --dump x.json   # 用本地 dump 重建（不联网）
"""

import argparse
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

UA = "RoamRadio/0.1 (+https://sdlyingyong.github.io/radio/)"
MIRRORS = [
    "https://de1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")

GENRES = [
    ("pop", "流行", "Pop"),
    ("rock", "摇滚", "Rock"),
    ("electronic", "电子", "Electronic"),
    ("hiphop", "嘻哈", "Hip-hop"),
    ("jazz", "爵士蓝调", "Jazz & Blues"),
    ("classical", "古典", "Classical"),
    ("news", "新闻谈话", "News & Talk"),
    ("folk", "乡村民谣", "Folk & Country"),
    ("world", "世界音乐", "World"),
    ("oldies", "怀旧金曲", "Oldies"),
    ("culture", "文化教育", "Culture"),
    ("other", "其他", "Other"),
]
GIDX = {g[0]: i for i, g in enumerate(GENRES)}

RULES = [
    ("news", "news talk speech information noticias aktuell politique politique-info radionews info debate interview"),
    ("classical", "classical klassik klassiek opera symphony chamber baroque chambermusic"),
    ("jazz", "jazz blues soul funk swing gospel rnb-soul motown"),
    ("rock", "rock metal punk indie alternative grunge hardcore ska hardrock heavy"),
    ("electronic", "electronic techno house trance dance edm club ambient chillout chill "
                   "drum dubstep synth electro hardstyle psytrance progressive beat"),
    ("hiphop", "hiphop hip-hop rap rnb r&b urban trap drill grime"),
    ("pop", "pop top40 top-40 hits chart mainstream schlager hot100"),
    ("folk", "country folk acoustic americana bluegrass singer-songwriter singer songwriter"),
    ("world", "world latin salsa reggae afro bollywood asian k-pop kpop j-pop jpop arabic "
              "orient ethnic tropical balkan flamenco tango chinese cantonese mandarin "
              "thai vietnamese indian persian turkish greek italian french german russian "
              "brazilian samba bossa celtic"),
    ("oldies", "oldies retro 60s 70s 80s 90s 50s evergreen classic-hits nostal"),
    ("culture", "culture arts art education religion sport comedy audiobook kids family "
                "history science health talk-radio lifestyle"),
]
RULES = [(g, set(kw.split())) for g, kw in RULES]

LANGS = {
    "english": "英语", "french": "法语", "german": "德语", "spanish": "西班牙语",
    "italian": "意大利语", "turkish": "土耳其语", "russian": "俄语",
    "portuguese": "葡萄牙语", "dutch": "荷兰语", "greek": "希腊语", "polish": "波兰语",
    "swedish": "瑞典语", "norwegian": "挪威语", "danish": "丹麦语", "finnish": "芬兰语",
    "czech": "捷克语", "hungarian": "匈牙利语", "romanian": "罗马尼亚语",
    "ukrainian": "乌克兰语", "arabic": "阿拉伯语", "hindi": "印地语", "chinese": "中文",
    "japanese": "日语", "korean": "韩语", "thai": "泰语", "vietnamese": "越南语",
    "indonesian": "印尼语", "malay": "马来语", "persian": "波斯语", "hebrew": "希伯来语",
    "catalan": "加泰罗尼亚语", "serbian": "塞尔维亚语", "croatian": "克罗地亚语",
    "bulgarian": "保加利亚语", "slovak": "斯洛伐克语", "slovenian": "斯洛文尼亚语",
    "lithuanian": "立陶宛语", "latvian": "拉脱维亚语", "estonian": "爱沙尼亚语",
    "icelandic": "冰岛语", "irish": "爱尔兰语", "welsh": "威尔士语", "bengali": "孟加拉语",
    "tamil": "泰米尔语", "telugu": "泰卢固语", "urdu": "乌尔都语", "tagalog": "他加禄语",
    "swahili": "斯瓦希里语", "amharic": "阿姆哈拉语", "azerbaijani": "阿塞拜疆语",
    "georgian": "格鲁吉亚语", "armenian": "亚美尼亚语", "albanian": "阿尔巴尼亚语",
    "macedonian": "马其顿语", "bosnian": "波斯尼亚语", "belarusian": "白俄罗斯语",
    "uzbek": "乌兹别克语", "kazakh": "哈萨克语", "mongolian": "蒙古语", "nepali": "尼泊尔语",
    "sinhala": "僧伽罗语", "khmer": "高棉语", "lao": "老挝语", "burmese": "缅甸语",
    "malayalam": "马拉雅拉姆语", "kannada": "卡纳达语", "marathi": "马拉地语",
    "gujarati": "古吉拉特语", "punjabi": "旁遮普语", "norwegian bokmal": "挪威语",
    "hausa": "豪萨语", "yoruba": "约鲁巴语", "zulu": "祖鲁语", "afrikaans": "南非荷兰语",
}

CC_ZH = """
CN 中国 HK 中国香港 MO 中国澳门 TW 中国台湾 US 美国 GB 英国 FR 法国 DE 德国
IT 意大利 ES 西班牙 PT 葡萄牙 NL 荷兰 BE 比利时 CH 瑞士 AT 奥地利 SE 瑞典
NO 挪威 DK 丹麦 FI 芬兰 IS 冰岛 IE 爱尔兰 PL 波兰 CZ 捷克 SK 斯洛伐克
HU 匈牙利 RO 罗马尼亚 BG 保加利亚 GR 希腊 HR 克罗地亚 RS 塞尔维亚 SI 斯洛文尼亚
BA 波黑 MK 北马其顿 AL 阿尔巴尼亚 EE 爱沙尼亚 LV 拉脱维亚 LT 立陶宛
RU 俄罗斯 UA 乌克兰 BY 白俄罗斯 MD 摩尔多瓦 GE 格鲁吉亚 AM 亚美尼亚
AZ 阿塞拜疆 KZ 哈萨克斯坦 UZ 乌兹别克斯坦 KG 吉尔吉斯斯坦 TJ 塔吉克斯坦
MN 蒙古 JP 日本 KR 韩国 KP 朝鲜 IN 印度 PK 巴基斯坦 BD 孟加拉国 LK 斯里兰卡
NP 尼泊尔 MM 缅甸 TH 泰国 LA 老挝 KH 柬埔寨 VN 越南 MY 马来西亚 SG 新加坡
ID 印尼 PH 菲律宾 BN 文莱 TL 东帝汶 AU 澳大利亚 NZ 新西兰 PG 巴布亚新几内亚
FJ 斐济 TR 土耳其 IR 伊朗 IQ 伊拉克 IL 以色列 SA 沙特阿拉伯 AE 阿联酋
QA 卡塔尔 KW 科威特 BH 巴林 OM 阿曼 JO 约旦 LB 黎巴嫩 SY 叙利亚 YE 也门
EG 埃及 MA 摩洛哥 DZ 阿尔及利亚 TN 突尼斯 LY 利比亚 SD 苏丹 ET 埃塞俄比亚
KE 肯尼亚 TZ 坦桑尼亚 UG 乌干达 NG 尼日利亚 GH 加纳 CI 科特迪瓦 SN 塞内加尔
CM 喀麦隆 ZA 南非 ZW 津巴布韦 ZM 赞比亚 MZ 莫桑比克 AO 安哥拉 NA 纳米比亚
BW 博茨瓦纳 MU 毛里求斯 MG 马达加斯加 RW 卢旺达 SO 索马里
BR 巴西 AR 阿根廷 CL 智利 CO 哥伦比亚 PE 秘鲁 VE 委内瑞拉 EC 厄瓜多尔
BO 玻利维亚 PY 巴拉圭 UY 乌拉圭 MX 墨西哥 GT 危地马拉 CR 哥斯达黎加
PA 巴拿马 CU 古巴 DO 多米尼加 HT 海地 JM 牙买加 TT 特立尼达和多巴哥
PR 波多黎各 BS 巴哈马 BB 巴巴多斯 CA 加拿大 GL 格陵兰
"""

def cc_map():
    out, toks = {}, CC_ZH.split()
    for i in range(0, len(toks) - 1, 2):
        out[toks[i]] = toks[i + 1]
    return out

CC_ZH_MAP = cc_map()
TAG_SPLIT = re.compile(r"[,;/|]")
NAME_CLEAN = re.compile(r"\s+")
NONWORD = re.compile(r"[^a-z0-9]+")


def fetch_all(dump=None):
    if dump:
        with open(dump, encoding="utf-8") as f:
            return json.load(f)

    base = ("/json/stations/search?hidebroken=true&order=votes&reverse=true")
    page = 5000
    offsets = list(range(0, 70000, page))

    def one(off):
        url = f"{MIRRORS[0]}{base}&limit={page}&offset={off}"
        for m in MIRRORS:
            try:
                req = urllib.request.Request(url.replace(MIRRORS[0], m),
                                             headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception:
                continue
        return []

    out = []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as ex:
        for i, chunk in enumerate(ex.map(one, offsets)):
            out.extend(chunk)
            print(f"  第 {i+1}/{len(offsets)} 页 · 累计 {len(out)} 条", file=sys.stderr)
            if not chunk:
                break
    return out


def genre_of(tags):
    tags = " ".join(TAG_SPLIT.split(tags.lower())) if tags else ""
    if not tags:
        return GIDX["other"]
    words = set(re.split(r"[^a-z0-9&]+", tags))
    for g, kw in RULES:
        if words & kw:
            return GIDX[g]
    return GIDX["other"]


def lang_of(raw):
    if not raw:
        return -1
    for item in TAG_SPLIT.split(raw.lower()):
        item = item.strip()
        if item in LANGS:
            return item
    first = TAG_SPLIT.split(raw.lower())[0].strip()
    return first or -1


def clean_name(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return NAME_CLEAN.sub(" ", s).strip()[:90]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="本地 station dump（json 数组），不联网")
    args = ap.parse_args()

    print("抓取 Radio Browser …", file=sys.stderr)
    raw = fetch_all(args.dump)
    if not args.dump:
        try:
            with open(os.path.join(HERE, ".raw_cache.json"), "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
        except Exception as e:
            print(f"  ! 原始缓存没写成功（不影响本次生成）：{e}", file=sys.stderr)
    print(f"原始 {len(raw)} 条", file=sys.stderr)

    seen, rows = set(), []
    for s in raw:
        name = clean_name(s.get("name"))
        url = (s.get("url_resolved") or s.get("url") or "").strip().replace(" ", "")
        if not name or not url.lower().startswith(("http://", "https://")):
            continue
        host = url.split("/")[2].lower() if url.count("/") >= 2 else url
        key = (NONWORD.sub("", name.lower())[:40], host)
        if key in seen:
            continue
        seen.add(key)
        lat = lng = None
        try:
            la = float(s.get("geo_lat"))
            lo = float(s.get("geo_long"))
            if -90 <= la <= 90 and -180 <= lo <= 180:
                lat, lng = la, lo
        except (TypeError, ValueError):
            pass
        rows.append({
            "name": name,
            "url": url,
            "lat": lat,
            "lng": lng,
            "cc": (s.get("countrycode") or "").upper()[:2],
            "country": (s.get("country") or "").strip(),
            "region": ("" if (s.get("state") or "").strip() in
                       ("-", "--", "N/A", "n/a", "NA", "Unknown", "unknown", "undefined")
                       else (s.get("state") or "").strip()),
            "tags": s.get("tags") or "",
            "lang": s.get("language") or "",
            "bitrate": int(s.get("bitrate") or 0),
            "codec": (s.get("codec") or "").upper(),
            "votes": int(s.get("votes") or 0),
            "clicks": int(s.get("clickcount") or 0),
            "geo": None,
        })

    exact = sum(1 for r in rows if r["lat"] is not None)
    print(f"去重后 {len(rows)} 条，其中 {exact} 条有精确坐标", file=sys.stderr)

    # ---- 无坐标的台按「州中心 → 国家中心」回退定位 ----
    def centers(keyfn):
        acc = {}
        for r in rows:
            if r["lat"] is None:
                continue
            k = keyfn(r)
            if k is None:
                continue
            a = acc.setdefault(k, [0.0, 0.0, 0])
            a[0] += r["lat"]; a[1] += r["lng"]; a[2] += 1
        return {k: (v[0]/v[2], v[1]/v[2]) for k, v in acc.items()}

    state_c = centers(lambda r: (r["cc"], r["region"]) if r["region"] else None)
    country_c = centers(lambda r: r["cc"] or None)

    dropped = 0
    for r in rows:
        if r["lat"] is not None:
            r["geo"] = 0
            continue
        k = (r["cc"], r["region"])
        if k in state_c:
            r["lat"], r["lng"] = state_c[k]; r["geo"] = 1
        else:
            # 只到国家一级的台不放了：国家中心会把几百个台压成一个假星团，
            # 宁可在这一块空着，也不要骗人的位置
            r["geo"] = -1
            dropped += 1

    rows = [r for r in rows if r["geo"] >= 0]
    g1 = sum(1 for r in rows if r["geo"] == 1)
    print(f"定位后 {len(rows)} 条：精确 {exact} · 州中心 {g1} · 丢弃 {dropped}",
          file=sys.stderr)

    # ---- 索引表 ----
    cc_list, cc_idx = [], {}
    region_list, region_idx = [], {}
    lang_list, lang_idx = [], {}

    def idx(table, map_, key):
        if key in map_:
            return map_[key]
        map_[key] = len(table)
        table.append(key)
        return map_[key]

    core_lat, core_lng, core_cc, core_g, core_lg, core_rg, core_br = [], [], [], [], [], [], []
    core_geo = []
    names, urls, flags = [], [], []

    for r in rows:
        core_lat.append(round(r["lat"] * 100))
        core_lng.append(round(r["lng"] * 100))
        cc = r["cc"]
        if cc and cc not in cc_idx:
            cc_idx[cc] = len(cc_list)
            cc_list.append([cc, CC_ZH_MAP.get(cc, r["country"] or cc), r["country"] or cc])
        core_cc.append(cc_idx.get(cc, -1))
        core_g.append(genre_of(r["tags"]))
        lg = lang_of(r["lang"])
        core_lg.append(idx(lang_list, lang_idx, lg) if lg != -1 else -1)
        core_rg.append(idx(region_list, region_idx, r["region"]) if r["region"] else -1)
        core_br.append(min(r["bitrate"], 512))
        core_geo.append(r["geo"])
        names.append(r["name"])
        urls.append(r["url"])
        flags.append(1 if r["url"].startswith("https://") else 0)

    lang_out = [[k, LANGS.get(k, k), k] for k in lang_list]

    core = {
        "v": 1,
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n": len(rows),
        "countries": cc_list,
        "langs": lang_out,
        "genres": [[g[0], g[1], g[2]] for g in GENRES],
        "regions": region_list,
        "lat": core_lat,
        "lng": core_lng,
        "cc": core_cc,
        "g": core_g,
        "lg": core_lg,
        "rg": core_rg,
        "br": core_br,
        "geo": core_geo,
    }
    meta = {"nm": names, "u": urls, "s": flags}

    os.makedirs(DATA, exist_ok=True)
    for fn, obj in (("core.json", core), ("meta.json", meta)):
        p = os.path.join(DATA, fn)
        blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
        with open(p, "wb") as f:
            f.write(blob)
        gz = len(gzip.compress(blob, 9))
        print(f"  {fn:10s} {len(blob)/1024:8.0f} KB  (gzip {gz/1024:6.0f} KB)", file=sys.stderr)

    https = sum(flags)
    print(f"电台 {len(rows)} · 国家 {len(cc_list)} · 地区 {len(region_list)} · "
          f"https 流 {https} ({https*100//max(len(rows),1)}%)", file=sys.stderr)


if __name__ == "__main__":
    main()
