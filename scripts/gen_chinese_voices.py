#!/usr/bin/env python3
"""Qwen3-TTS 中文配音全生命周期生成工具 (World of Claudecraft 本地化套件)

功能特性:
1. 【资源隔离】：输出至 public/audio/voice_zh/，避免与主仓库 public/audio/voice/ 产生 Git 二进制冲突。
2. 【内容寻址缓存】：基于 MD5(clean_text + speaker + instruct) 进行指纹校验，台词更改增量重跑，未变动台词 0ms 跳过。
3. 【断点续传与原子写入】：使用 .tmp 临时文件 + 校验后原子覆盖，任何意外中断均可无缝继续。
4. 【多维调试过滤】：支持 --status 查看概况、--only 关键词过滤、--limit 限制生成条数、--force 强制全量重跑。
"""

import argparse
import hashlib
import json
import concurrent.futures
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import soundfile as sf
    from gradio_client import Client
except ImportError:
    print("[Error] 请在 WSL 的 conda 环境中运行此脚本：")
    print("  conda activate qwen3_tts")
    print("  python scripts/gen_chinese_voices.py")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
VOICE_ZH_DIR = ROOT / "public" / "audio" / "voice_zh"
CACHE_FILE = ROOT / "scripts" / "voices" / "zh_voice_cache.json"
MANIFEST_ZH_FILE = ROOT / "src" / "game" / "voice_manifest.zh_CN.generated.ts"
MANIFEST_EN_FILE = ROOT / "src" / "game" / "voice_manifest.generated.ts"
ZH_LOCALE_FILE = ROOT / "src" / "ui" / "i18n.locales" / "zh_CN.ts"
PROMPTS_FILE = ROOT / "scripts" / "voices" / "npc_voice_prompts.mjs"

# 48 条战斗与护送大喊的优质中文翻译对照表
YELL_TRANSLATIONS = {
    # Nythraxis, Scourge of Thornpeak (古代龙王/君王 Boss)
    "yell__malric": "马尔里克...",
    "yell__what_have_you_done": "你都干了些什么！",
    "yell__another_kingdom_comes_to_challenge_me": "又一个王国妄图挑战我！",
    "yell__you_will_join_the_rest": "你们也将步其后尘！",
    "yell__i_built_a_kingdom": "我曾建立起一个王国...",
    "yell__i_will_not_lose_it_again": "我绝不会再次失去它！",
    "yell__kneel_before_your_king": "在你们的君王面前下跪！",
    "yell__rise_once_more": "再次站起来吧！",
    "yell__your_king_commands_it": "这是你们君王的命令！",
    "yell__another_priest": "又一个牧师...",
    "yell__your_spirit_belongs_to_me": "你的灵魂归我所有！",
    "yell__witness_true_eternity": "见证真正的永恒吧！",
    "yell__you_cannot_stop_what_was_promised": "你无法阻止早已注定的宿命...",

    # Brother Aldric (圣光大牧师团队盟友)
    "yell__your_kingdom_is_gone_nythraxis": "你的王国早已覆灭，奈斯拉西斯！",
    "yell__yet_you_still_cling_to_it": "可你却依旧执迷不悟！",
    "yell__champions_listen_carefully": "勇士们，仔细听好！",
    "yell__the_wardstones_still_bind_his_soul": "结界石依然束缚着他的灵魂。",
    "yell__when_the_time_comes_do_not_ignore_them": "时机一到，千万不要忽视它们！",
    "yell__fail_and_we_all_perish": "一旦失败，我们都将葬身于此！",

    # Ignivar Ashcaller (唤灰者·熔炉巨兽 Boss)
    "yell__i_am_the_seal_i_will_not_break": "我是封印本身。我绝不会破裂！",
    "yell__the_seal_hears_you_little_embers_step_closer_and_feed_the_la": "封印听到了你们的声音，微弱的余烬。靠近些，献祭给终焉之火吧。",
    "yell__ignivar_ashcaller_awakens_let_the_world_burn": "唤灰者伊格尼瓦尔苏醒了。让世界化为灰烬！",
    "yell__the_sky_itself_will_burn": "连天空都将燃烧！",
    "yell__the_last_flame_consumes_all": "终焉之火将吞噬一切！",
    "yell__varkhul_the_seal_is_broken": "瓦克胡尔... 封印碎了...",
    "yell__bear_the_last_flame_let_it_judge_you": "承受终焉之火吧。让烈焰审判你们！",
    "yell__the_old_wells_answer_to_my_fire": "古井在回应我的烈焰！",
    "yell__turn_with_the_flame_or_be_unmade": "顺应烈火，否则化为齑粉！",
    "yell__the_forge_rejects_you": "熔炉拒绝了你！",
    "yell__another_spark_extinguished": "又一颗火星熄灭了。",
    "yell__varkhul_forged_me_to_endure": "瓦克胡尔铸就我是为了让我永存！",

    # Varkhul, Forgefather of the Last Flame (终焉熔炉锻造之父 Boss)
    "yell__the_spring_did_not_die_i_bound_its_last_memory_into_iron": "泉水并未枯竭。我将它最后的记忆封入了钢铁。",
    "yell__you_call_it_a_prison_because_your_flesh_fears_endurance": "你称其为牢笼，只因你的血肉惧怕永恒。",
    "yell__i_am_varkhul_forgefather_of_the_last_flame_raise_your_weapon": "我是瓦克胡尔，终焉之火的锻造之父。举起你们的武器吧，微不足道的火星。",
    "yell__every_blow_will_feed_the_furnace_in_my_chest_by_ember_stone_": "每一次打击都会填满我胸膛中的熔炉。以余烬、顽石与铁砧之名，我将粉碎你们！",
    "yell__master_i_have_failed_you": "主人... 我辜负了你...",

    # 4 位护送 NPC 任务喊话 (Escorts: Bram, Wren, Mosley, Navigator)
    "yell__nell_sent_you_then_she_is_alive_oh_thank_the_tide_stay_close": "是内尔叫你来的？那她还活着，谢天谢地！跟紧点，朋友：那些小东西在这片海滩上搜寻，而且从来不落单。",
    "yell__gullhaven_i_can_see_our_roof_from_here_go_on_ahead_friend_i_": "鸥港！我在这儿都能看见我们家屋顶了。你先请吧，朋友，我还得去抱抱我妻子！",
    "yell__nell_i_am_sorry_love_i_nearly_made_it_home": "内尔... 对不起，亲爱的... 我差一点就到家了...",

    "yell__you_ll_walk_with_me_stay_close_please_the_wolves_have_been_c": "你愿意护送我吗？请跟紧我。天黑以来狼群就一直在周围打转。",
    "yell__the_lights_we_made_it_we_truly_made_it_thank_you_friend_i_ca": "有光！我们到了，我们真的成功了！谢谢你，朋友。从这里都能看见营地了。",
    "yell__no_i_m_sorry_brosk_i_couldn_t_make_it": "不... 对不起，布罗斯克... 我没能赶回去...",

    "yell__you_ll_walk_with_me_bless_you_keep_between_me_and_the_trees_": "你愿意和我一起走？愿你受到保佑。走在我和树林之间，要是听见号角声，我们就跑！",
    "yell__the_lanterns_i_can_hear_the_bells_the_proper_bells_i_am_neve": "灯笼！我听见钟声了，是真正的钟声。我再也不挖过膝深的坑了，朋友。谢谢你！",
    "yell__no_not_out_here_do_not_let_them_plant_me_where_the_candles_c": "不... 不要死在这里... 别让他们把我埋在烛光照不到的地方...",

    "yell__you_came_down_the_wreck_line_for_me_then_let_us_go_before_th": "你是顺着沉船线来找我的？那趁潮水还没涨赶快走吧。走在我和海水之间，那些螃蟹会从浪里冲出来。",
    "yell__drifthaven_i_can_smell_the_cookfires_from_here_i_owe_you_my_": "漂泊港！我都能闻到炊烟的味儿了。我的海图和这条命都多亏了你，朋友！",
    "yell__no_the_sea_spits_me_back_once_not_twice": "不... 大海能饶我一次，却饶不了第二次..."
}

# 默认配音映射规则 (根据角色身份、性别、性格与声线特征分配)
DEFAULT_SPEAKER = "👨 Uncle_Fu - 中文"
DEFAULT_INSTRUCT = "自然流畅的中世纪魔幻奇幻语气"

NPC_VOICE_CONFIG = {
    # 威严年长 / 军官 / 牧师
    "brother_aldric": ("👨 Uncle_Fu - 中文", "庄重慈悲的年长牧师语气，沉稳而充满使命感"),
    "marshal_redbrook": ("👨 Uncle_Fu - 中文", "饱经沙场的老元帅语气，低沉沙哑，带着军人威严"),
    "ferryman_odo": ("👨 Uncle_Fu - 中文", "慈祥温和的老船夫口吻，语调舒缓沉稳"),
    "warden_fenwick": ("👨 Uncle_Fu - 中文", "严肃警惕的守卫队长语气"),
    "gatecaptain_brannoc": ("👨 Uncle_Fu - 中文", "刚毅威严的要塞门将口吻"),
    
    # Boss / 巨兽 / 熔炉
    "nythraxis": ("👨 Uncle_Fu - 中文", "极度霸道低沉的古代暗黑君王巨龙咆哮口吻"),
    "ignivar": ("👨 Uncle_Fu - 中文", "烈焰与熔炉混响、狂暴充满压迫感的魔神语气"),
    "varkhul": ("👨 Uncle_Fu - 中文", "古老苍劲、坚如磐石的锻造之父沉重低音"),

    # 商人 / 市井 / 青年男性
    "the_merchant": ("🧑 Dylan - 中文(北京话)", "热情洋溢、精明能干的商人叫卖语气"),
    "trader_wilkes": ("🧑 Dylan - 中文(北京话)", "市井小贩热情的吆喝语气"),
    "auctioneer_voss": ("🧑 Dylan - 中文(北京话)", "节奏明快、充满诱惑力的拍卖商语气"),
    "card_master": ("🧑 Dylan - 中文(北京话)", "轻松戏谑、玩世不恭的卡牌大师语气"),
    "bursar_fernando": ("🧑 Dylan - 中文(北京话)", "干练严谨的年轻账房掌柜口吻"),

    # 粗犷男性 / 猎人 / 铁匠 / 工人
    "smith_haldren": ("👨 Uncle_Fu - 中文", "粗犷洪亮的铁匠打铁口吻"),
    "foreman_odell": ("👨 Uncle_Fu - 中文", "沙哑暴躁的矿工工头大嗓门"),
    "armorer_hode": ("👨 Uncle_Fu - 中文", "低沉有力的铠甲铸造大师语气"),
    "fisherman_brandt": ("🧑 Eric - 中文(四川话)", "有点迷糊怪异的老渔民语气"),
    "trapper_brosk": ("👨 Uncle_Fu - 中文", "老练冷峻的雪原猎人语气"),
    "gravedigger_mosley": ("🧑 Eric - 中文(四川话)", "战战兢兢、略带神经质的掘墓人口吻"),
    "castaway_navigator": ("🧑 Eric - 中文(四川话)", "劫后余生、疲惫急迫的水手口吻"),
    "fisher_bram": ("🧑 Dylan - 中文(北京话)", "真诚焦急的年轻渔民口吻"),

    # 干练女性 / 斥候 / 女队长
    "captain_thessaly": ("👩 Vivian - 中文", "英姿飒爽、威严果断的女卫队长命令语气"),
    "scout_maren": ("👩 Vivian - 中文", "机警短促、压低嗓音的敏捷女斥候口吻"),
    "quartermaster_bree": ("👩 Vivian - 中文", "利落高效的女军需官口吻"),
    "stablemaster_marla": ("👩 Vivian - 中文", "干练热情、爽朗的马厩老板娘语气"),
    "salvage_boss_ryna": ("👩 Vivian - 中文", "干练豪放的打捞队女首领口吻"),
    "warden_kaldra": ("👩 Vivian - 中文", "冷峻坚决的女守望者口吻"),

    # 温柔女性 / 草药师 / 观星者 / 治愈者
    "apothecary_lin": ("👩 Serena - 中文", "轻柔谨慎的女草药医师口吻，温和沉静"),
    "aurorist_veyla": ("👩 Serena - 中文", "空灵悠扬、宁静专注的极光学者口吻"),
    "mother_sedge": ("👩 Serena - 中文", "慈祥神秘的沼泽老妇人语气"),
    "lira_dewsong": ("👩 Serena - 中文", "清澈优美的精灵歌咏者语调"),
    "spirit_healer": ("👩 Serena - 中文", "飘渺神圣、超然物外的灵魂医者语气"),
    "apprentice_wren": ("👩 Serena - 中文", "惊慌失措、需要保护的年轻女学徒语气"),
    "weaver_amelle": ("👩 Serena - 中文", "温和细致的纺织女工口吻"),
}


def clean_spoken_text(text: str) -> str:
    """清理台词文本中的运行时插值变量与特殊字符，使朗读自然流畅"""
    cleaned = text
    # 替换玩家名称/职业变量
    cleaned = re.sub(r'\{playerName\}|\$N', '冒险者', cleaned)
    cleaned = re.sub(r'\{className\}|\$C', '冒险者', cleaned)
    cleaned = re.sub(r'\{[a-zA-Z0-9_]+\}', '', cleaned)  # 其余占位符若有则略过
    cleaned = re.sub(r'\$[a-zA-Z0-9_]', '', cleaned)
    # 合并多余空白
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def compute_fingerprint(text: str, speaker: str, instruct: str) -> str:
    """计算单条语音的配置指纹，用于变更检测"""
    h = hashlib.md5()
    h.update(text.encode('utf-8'))
    h.update(speaker.encode('utf-8'))
    h.update(instruct.encode('utf-8'))
    return h.hexdigest()[:16]


def compute_file_hash12(file_path: Path) -> str:
    """计算音频文件的 SHA256 前 12 位（与游戏引擎缓存机制完全一致）"""
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def load_manifest_keys() -> dict[str, str]:
    """从主仓库的 voice_manifest.generated.ts 中解析出全部 578 个 key 及其所属 npc"""
    if not MANIFEST_EN_FILE.exists():
        raise FileNotFoundError(f"找不到英文清单文件: {MANIFEST_EN_FILE}")
    content = MANIFEST_EN_FILE.read_text(encoding="utf-8")
    m = re.search(r'export const VOICE_LINES: Record<string, string> =\s*(\{[\s\S]*?\})\s*as const;', content)
    if not m:
        raise ValueError("无法解析 voice_manifest.generated.ts 中的 JSON 数据")
    raw_dict = json.loads(m.group(1))
    
    # 提取 key -> voiceNpc
    res = {}
    for key, val in raw_dict.items():
        m2 = re.match(r'/audio/voice/([^/]+)/', val)
        voice_npc = m2.group(1) if m2 else "unknown"
        res[key] = voice_npc
    return res


def load_all_chinese_lines(manifest_keys: dict[str, str]) -> dict[str, dict]:
    """匹配并组装全部 578 条音频的中文台词、角色、情绪指令"""
    zh_content = ZH_LOCALE_FILE.read_text(encoding="utf-8")
    
    # 解析 zh_CN.ts
    entries = {}
    pattern = re.compile(r"'(?P<key>[a-zA-Z0-9_.]+)':\s*(?:'(?P<sq>(?:\\'|[^'])*)'|`(?P<bt>(?:\\`|[^`])*)`)")
    for m in pattern.finditer(zh_content):
        k = m.group('key')
        v = m.group('sq') if m.group('sq') is not None else m.group('bt')
        entries[k] = v.replace("\\'", "'").replace('\\"', '"').replace('\\n', '\n')

    # 引导员 Ferryman Odo 映射
    guide_map = {
        'guide__odo__arrival': entries.get('hudChrome.bootcamp.voiceArrival'),
        'guide__odo__first_flag': entries.get('hudChrome.bootcamp.voiceFirstFlag'),
        'guide__odo__run_done': entries.get('hudChrome.bootcamp.voiceRunDone'),
        'guide__odo__station_done_a': entries.get('hudChrome.bootcamp.voiceStationDoneA'),
        'guide__odo__station_done_b': entries.get('hudChrome.bootcamp.voiceStationDoneB'),
        'guide__odo__veer_off': entries.get('hudChrome.bootcamp.voiceVeerOff'),
        'guide__odo__graduate': entries.get('hudChrome.bootcamp.voiceGraduate'),
    }

    catalog = {}
    for line_key, voice_npc in manifest_keys.items():
        text = None
        if line_key.startswith('greeting__'):
            nid = line_key.replace('greeting__', '')
            text = entries.get(f'entities.npcs.{nid}.greeting')
        elif line_key.startswith('quest__') and line_key.endswith('__offer'):
            qid = line_key[len('quest__'):-len('__offer')]
            text = entries.get(f'entities.quests.{qid}.text')
        elif line_key.startswith('quest__') and line_key.endswith('__complete'):
            qid = line_key[len('quest__'):-len('__complete')]
            text = entries.get(f'entities.quests.{qid}.completion')
        elif line_key in guide_map:
            text = guide_map[line_key]
        elif line_key in YELL_TRANSLATIONS:
            text = YELL_TRANSLATIONS[line_key]

        if not text:
            print(f"[Warn] 未能找到中文文本: {line_key} (voiceNpc: {voice_npc})")
            text = "你好，旅行者。"  # 保底文本

        clean_text = clean_spoken_text(text)
        speaker, instruct = NPC_VOICE_CONFIG.get(voice_npc, (DEFAULT_SPEAKER, DEFAULT_INSTRUCT))
        fingerprint = compute_fingerprint(clean_text, speaker, instruct)
        
        catalog[line_key] = {
            "key": line_key,
            "voice_npc": voice_npc,
            "text": clean_text,
            "speaker": speaker,
            "instruct": instruct,
            "fingerprint": fingerprint,
            "dest_rel": f"{voice_npc}/{line_key}.mp3"
        }
    return catalog


def load_cache() -> dict[str, dict]:
    """读取已有的增量缓存记录"""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: dict[str, dict]):
    """原子更新保存缓存记录"""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(CACHE_FILE)


def update_manifest_file(manifest_keys: dict[str, str], out_dir: Path):
    """根据实际在磁盘上生成的音频文件重新生成 voice_manifest.zh_CN.generated.ts"""
    entries = {}
    for line_key, voice_npc in manifest_keys.items():
        mp3_path = out_dir / voice_npc / f"{line_key}.mp3"
        if mp3_path.exists() and mp3_path.stat().st_size > 1024:
            h12 = compute_file_hash12(mp3_path)
            # 路径使用独立的前缀 /audio/voice_zh/
            entries[line_key] = f"/audio/voice_zh/{voice_npc}/{line_key}.mp3?v={h12}"

    sorted_entries = dict(sorted(entries.items()))
    lines = [
        "// Generated by scripts/gen_chinese_voices.py. Do not edit by hand.",
        "// Maps an NPC voice-line key to its localized Chinese audio path.",
        "export const VOICE_LINES_ZH: Record<string, string> = ",
        f"{json.dumps(sorted_entries, indent=2)} as const;",
        ""
    ]
    MANIFEST_ZH_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = MANIFEST_ZH_FILE.with_suffix(".tmp")
    tmp_file.write_text("\n".join(lines), encoding="utf-8")
    tmp_file.replace(MANIFEST_ZH_FILE)
    print(f"\n[Manifest] 已更新中文语音清单: {MANIFEST_ZH_FILE.relative_to(ROOT)} ({len(sorted_entries)}/{len(manifest_keys)} 条可用)")


def get_tts_client(api_url: str) -> Client:
    """创建或重建 Gradio Client"""
    return Client(api_url)


def run_predict_with_timeout(client: Client, item: dict, timeout_sec: int = 45):
    """带超时控制的单次调用"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            client.predict,
            text=item["text"],
            language_label="中文 / Chinese",
            instruct=item["instruct"],
            max_new_tokens=2048,
            api_name="/synth_voicedesign"
        )
        return future.result(timeout=timeout_sec)


def synthesize_single_line(client_ref: list, api_url: str, item: dict, dest_path: Path, max_retries: int = 3) -> str:
    """调用本地 Qwen3-TTS 合成单条音频（支持超时熔断与连接重置）"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp3 = dest_path.with_suffix(".tmp.mp3")

    for attempt in range(max_retries):
        try:
            client = client_ref[0]
            res = run_predict_with_timeout(client, item, timeout_sec=45)
            wav_path = res[1]
            if not wav_path or not Path(wav_path).exists():
                raise RuntimeError(f"TTS 服务未返回有效音频路径: {res}")
            
            # 读取 wav 并以 44.1kHz MP3 格式写入
            data, sr = sf.read(wav_path)
            sf.write(str(tmp_mp3), data, sr, format="MP3")

            # 校验大小
            if tmp_mp3.stat().st_size < 1024:
                raise RuntimeError("生成的 MP3 文件异常过小")

            # 原子替换
            tmp_mp3.replace(dest_path)
            return compute_file_hash12(dest_path)
        except Exception as e:
            if tmp_mp3.exists():
                tmp_mp3.unlink(missing_ok=True)
            # 异常时尝试重置 client 连接
            try:
                client_ref[0] = get_tts_client(api_url)
            except Exception:
                pass
            if attempt < max_retries - 1:
                wait_sec = 2 * (attempt + 1)
                print(f"\n  [Retry] 生成异常 ({type(e).__name__}: {e})，重置连接并在 {wait_sec}s 后重试...", end="", flush=True)
                time.sleep(wait_sec)
            else:
                raise e

def main():
    parser = argparse.ArgumentParser(description="World of Claudecraft Qwen3-TTS 本地中文语音生成工具")
    parser.add_argument("--api-url", default="http://127.0.0.1:7860", help="Qwen3-TTS 服务 URL (默认 http://127.0.0.1:7860)")
    parser.add_argument("--target-dir", default=str(VOICE_ZH_DIR), help="输出音频目录 (默认 public/audio/voice_zh)")
    parser.add_argument("--status", action="store_true", help="仅查看当前语音库状态与待生成统计，不调用 TTS")
    parser.add_argument("--only", type=str, default=None, help="仅合成包含指定关键字的 lineKey 或 npcId")
    parser.add_argument("--limit", type=int, default=None, help="单次最大生成音频条数")
    parser.add_argument("--force", action="store_true", help="强制全量重新合成（忽略缓存）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将要合成的任务，不实际生成")
    args = parser.parse_args()

    target_dir = Path(args.target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    print("==================================================================")
    print("  🎙️  World of Claudecraft 中文语音构建管道 (Qwen3-TTS) ")
    print("==================================================================")
    
    manifest_keys = load_manifest_keys()
    print(f"[*] 扫描到游戏标准清单条目: {len(manifest_keys)} 条")
    
    catalog = load_all_chinese_lines(manifest_keys)
    cache = load_cache()
    
    # 筛选需要生成的条目
    pending = []
    cached_count = 0
    changed_count = 0
    missing_count = 0

    for key, item in catalog.items():
        if args.only and args.only not in key and args.only not in item["voice_npc"]:
            continue

        dest_file = target_dir / item["voice_npc"] / f"{key}.mp3"
        cached_entry = cache.get(key)
        
        needs_generate = False
        reason = ""

        if args.force:
            needs_generate = True
            reason = "强制生成(--force)"
        elif not dest_file.exists() or dest_file.stat().st_size < 1024:
            needs_generate = True
            missing_count += 1
            reason = "文件缺失或未生成"
        elif not cached_entry or cached_entry.get("text_hash") != item["fingerprint"]:
            needs_generate = True
            changed_count += 1
            reason = "台词或音色已修改(指纹变动)"
        else:
            cached_count += 1

        if needs_generate:
            pending.append((item, dest_file, reason))

    print(f"[*] 缓存有效且完备: {cached_count} 条")
    print(f"[*] 待生成/待更新: {len(pending)} 条 (缺失: {missing_count}, 改动: {changed_count})")

    if args.status:
        print("\n--- 待合成列表预览 (前 15 条) ---")
        for item, dest, r in pending[:15]:
            print(f"  [{r:18s}] {item['key']:<50s} -> {item['voice_npc']} ({len(item['text'])}字: {item['text'][:20]}...)")
        if len(pending) > 15:
            print(f"  ... 还有 {len(pending) - 15} 条")
        return

    if not pending:
        print("\n✨ 所有语音均已处于最新状态，无需重新生成！")
        update_manifest_file(manifest_keys, target_dir)
        return

    if args.limit:
        pending = pending[:args.limit]
        print(f"[*] 已应用 --limit 限制，本次仅处理前 {len(pending)} 条")

    if args.dry_run:
        print("\n[Dry Run] 计划生成的任务：")
        for item, dest, r in pending:
            print(f"  - {item['key']} ({item['voice_npc']}): \"{item['text']}\" [{r}]")
        return

    # 初始化 TTS Client
    print(f"\n[*] 正在连接本地 Qwen3-TTS 服务: {args.api_url} ...")
    try:
        client_ref = [get_tts_client(args.api_url)]
        print("[*] 连接成功！开始进行增量语音合成...")
    except Exception as e:
        print(f"[Error] 无法连接到 Qwen3-TTS 服务: {e}")
        print("请确认 http://localhost:7860/ 正在运行。")
        sys.exit(1)

    success = 0
    failed = 0
    t_start = time.time()

    for idx, (item, dest_file, reason) in enumerate(pending, 1):
        print(f"[{idx}/{len(pending)}] {item['key']} ({item['voice_npc']}, {len(item['text'])}字) [{reason}] ... ", end="", flush=True)
        t0 = time.time()
        try:
            h12 = synthesize_single_line(client_ref, args.api_url, item, dest_file)
            dt = time.time() - t0
            print(f"OK ({dt:.1f}s)")
            
            # 及时更新 cache
            cache[item["key"]] = {
                "text": item["text"],
                "text_hash": item["fingerprint"],
                "speaker": item["speaker"],
                "instruct": item["instruct"],
                "audio_path": str(dest_file.relative_to(target_dir)),
                "audio_hash": h12,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            save_cache(cache)
            success += 1
        except KeyboardInterrupt:
            print("\n[Interrupted] 收到用户中断信号！当前进度已保存，下次运行可断点继续。")
            break
        except Exception as e:
            print(f"FAILED: {e}")
            failed += 1

    total_time = time.time() - t_start
    print("\n==================================================================")
    print(f"  🏁 处理完成: 成功 {success} 条, 失败 {failed} 条, 总耗时 {total_time:.1f}s")
    print("==================================================================")
    
    # 刷新中文清单文件
    update_manifest_file(manifest_keys, target_dir)


if __name__ == "__main__":
    main()
