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
    "yell__malric": "马尔里克……！",
    "yell__what_have_you_done": "你……你究竟干了些什么！",
    "yell__another_kingdom_comes_to_challenge_me": "又一个不知死活的凡人王国，妄图挑战朕的威严！",
    "yell__you_will_join_the_rest": "你们这群蝼蚁，也将步其后尘，葬身于此！",
    "yell__i_built_a_kingdom": "朕曾亲手缔造万世帝国……",
    "yell__i_will_not_lose_it_again": "朕绝不会……再次失去它！绝不！",
    "yell__kneel_before_your_king": "在你们的真王面前跪下！",
    "yell__rise_once_more": "再度苏醒吧，我的仆从！",
    "yell__your_king_commands_it": "这是尔等君王的无上圣裁！",
    "yell__another_priest": "又一个自诩虔诚的神棍……",
    "yell__your_spirit_belongs_to_me": "你的灵魂，归我所有！",
    "yell__witness_true_eternity": "在深渊中，见证真正的永恒吧！",
    "yell__you_cannot_stop_what_was_promised": "凡人……你无法阻挡早已注定的末日宿命！",

    # Brother Aldric (圣光大牧师团队盟友)
    "yell__your_kingdom_is_gone_nythraxis": "你的帝国早已化为尘土，奈斯拉西斯！",
    "yell__yet_you_still_cling_to_it": "可你这可悲的亡魂，却依旧执迷不悟！",
    "yell__champions_listen_carefully": "勇士们，仔细听好！",
    "yell__the_wardstones_still_bind_his_soul": "远古结界石依然在禁锢着他的残魂！",
    "yell__when_the_time_comes_do_not_ignore_them": "封印显现之时，千万不可分神！",
    "yell__fail_and_we_all_perish": "一旦结界破损，我们全都要葬身于此！",

    # Ignivar Ashcaller (唤灰者·熔炉巨兽 Boss)
    "yell__i_am_the_seal_i_will_not_break": "我即是封印本身！坚不可摧，永世不灭！",
    "yell__the_seal_hears_you_little_embers_step_closer_and_feed_the_la": "封印已听闻尔等的战栗，卑微的余烬！靠近些……化作终焉之火的祭品吧！",
    "yell__ignivar_ashcaller_awakens_let_the_world_burn": "唤灰者伊格尼瓦尔已然苏醒！让整个世界……化为灰烬！",
    "yell__the_sky_itself_will_burn": "连苍穹天幕……都将燃尽！",
    "yell__the_last_flame_consumes_all": "终焉之火，将吞噬一切！",
    "yell__varkhul_the_seal_is_broken": "瓦克胡尔……封印……碎了……",
    "yell__bear_the_last_flame_let_it_judge_you": "承受终焉烈焰吧！在烈火的审判下灰飞烟灭！",
    "yell__the_old_wells_answer_to_my_fire": "古老地脉……正在回应我的怒火！",
    "yell__turn_with_the_flame_or_be_unmade": "顺从烈焰的洪流，否则化为齑粉！",
    "yell__the_forge_rejects_you": "远古熔炉拒绝了你！",
    "yell__another_spark_extinguished": "又一颗微弱的火星……熄灭了。",
    "yell__varkhul_forged_me_to_endure": "瓦克胡尔锻造我的身躯，是为了让我与世长存！",

    # Varkhul, Forgefather of the Last Flame (终焉熔炉锻造之父 Boss)
    "yell__the_spring_did_not_die_i_bound_its_last_memory_into_iron": "活泉从未干涸！我将其最后的残存记忆，永久铸入了玄铁！",
    "yell__you_call_it_a_prison_because_your_flesh_fears_endurance": "尔等称其为牢狱，只因凡胎血肉……惧怕永恒的磨砺！",
    "yell__i_am_varkhul_forgefather_of_the_last_flame_raise_your_weapon": "吾乃瓦克胡尔，终焉烈焰的锻造之父！举起你们的凡铁吧，微弱的火星！",
    "yell__every_blow_will_feed_the_furnace_in_my_chest_by_ember_stone_": "每一记重击，都将化作吾胸膛熔炉的烈焰！以余烬、顽石与巨砧之名，吾将重铸你们的形体！",
    "yell__master_i_have_failed_you": "主人……老仆……有负所托……",

    # 4 位护送 NPC 任务喊话 (Escorts: Bram, Wren, Mosley, Navigator)
    "yell__nell_sent_you_then_she_is_alive_oh_thank_the_tide_stay_close": "是内尔托你来寻我的？她还活着……哦，感谢海神！跟紧点，朋友：滩涂上的那些怪物从来不会落单！",
    "yell__gullhaven_i_can_see_our_roof_from_here_go_on_ahead_friend_i_": "鸥港！我在这儿都能看见自家的屋顶了！你先请吧朋友，我得赶紧飞奔回去拥抱我的妻子！",
    "yell__nell_i_am_sorry_love_i_nearly_made_it_home": "内尔……对不起，亲爱的……我差一点点……就能回家了……",

    "yell__you_ll_walk_with_me_stay_close_please_the_wolves_have_been_c": "你愿意护送我走这一程吗？求你跟紧些……入夜以来，饥饿的狼群就一直在周围阴魂不散！",
    "yell__the_lights_we_made_it_we_truly_made_it_thank_you_friend_i_ca": "营火的光芒！我们走出来了，我们真的活下来了！谢谢你，朋友，从这儿已经能看清大营了！",
    "yell__no_i_m_sorry_brosk_i_couldn_t_make_it": "不……对不起，布罗斯克大师……我没能把药剂送回去……",

    "yell__you_ll_walk_with_me_bless_you_keep_between_me_and_the_trees_": "你愿意陪我一起穿过密林？愿圣光庇佑你！走在我和林木之间，要是听见雾里吹响号角，咱们就拼命跑！",
    "yell__the_lanterns_i_can_hear_the_bells_the_proper_bells_i_am_neve": "长明灯！我听见钟声了，是教堂那口神圣的大钟！我这辈子再也不挖过膝深的坑了，朋友，大恩大德永世难忘！",
    "yell__no_not_out_here_do_not_let_them_plant_me_where_the_candles_c": "不……不要死在荒郊野外……别让他们把我埋在蜡烛照不到的黑暗里……",

    "yell__you_came_down_the_wreck_line_for_me_then_let_us_go_before_th": "你是顺着沉船残骸一路找过来的？快，趁着怒潮还没漫上来！紧挨着我和海水，那些狂暴的潜伏蟹随时会破浪而出！",
    "yell__drifthaven_i_can_smell_the_cookfires_from_here_i_owe_you_my_": "避风港！我都闻到炊烟里热汤的香气了！我的航海图和这条老命，全都是你给的，朋友！",
    "yell__no_the_sea_spits_me_back_once_not_twice": "不……无情的大海能饶我一次，却绝不会仁慈第二次……"
}

# 全量 92 位 NPC 专属 VoiceDesign 声音指导词库 (基于官方原版人设提取)
DEFAULT_INSTRUCT = "自然流畅的中世纪奇幻冒险者口吻，清晰生动"
NPC_VOICE_INSTRUCTS = {
    'alchemist_verane': '30多岁至40岁的高冷女药剂大师，冷峻克制、咬字精准干练的女中音，带着严谨威严的成熟女性嗓音',
    'apothecary_lin': '30多岁至40岁轻柔谨慎的女草药医师，嗓音温和清润、带着细致关切的女中音',
    'apprentice_wren': '年轻怯生生、有些慌乱的见习女学徒嗓音',
    'archivist_tullo': '60多岁老年热情精明的商人小贩，语速明快、亲切流畅的市井男性嗓音',
    'armorer_hode': '50多岁成熟自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'astronomer_cassian': '40多岁中年热情精明的商人小贩，语速明快、亲切流畅的市井男性嗓音',
    'auctioneer_voss': '节奏明快、充满诱惑力与市井喜感的拍卖商口吻',
    'aurorist_veyla': '空灵悠扬、宁静专注的极光学者女性口吻',
    'bellkeeper_tam': '50多岁成熟饱经沧桑的长者，声音沉稳和蔼、语调舒缓的中老年男性男低音',
    'bridgewright_alden': '40多岁中年威严刚毅的军人，低沉有力、沉稳干练的成年男性男中音',
    'brother_aldric': '60多岁庄重慈悲的圣光大牧师，饱经沧桑、沉稳肃穆的长者男中音',
    'brother_halven': '40多岁中年自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'bursar_aldous_crane': '60多岁老年热情精明的商人小贩，语速明快、亲切流畅的市井男性嗓音',
    'bursar_fernando': '40多岁中年威严刚毅的军人，低沉有力、沉稳干练的成年男性男中音',
    'bursar_petra_vell': '金库女司库主管，精明干练、咬字干脆利落的成熟职场女性中音',
    'captain_thessaly': '英姿飒爽、威严果断的要塞女卫队长，坚决洪亮的军官女性口吻',
    'card_master': '轻松戏谑、玩世不恭的年轻卡牌大师口吻',
    'castaway_navigator': '30多岁自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'chronicler_edda_hartwell': '年轻的高山女学者，语速轻快敏锐、朝气蓬勃且求知欲强的年轻女性清脆嗓音',
    'chronicler_osric_fenn': '40多岁中年热情精明的商人小贩，语速明快、亲切流畅的市井男性嗓音',
    'chronicler_saul': '50多岁成熟威严刚毅的军人，低沉有力、沉稳干练的成年男性男中音',
    'cook_marlow': '40多岁中年威严刚毅的军人，低沉有力、沉稳干练的成年男性男中音',
    'ferryman_odo': '60多岁老年自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'ferrymaster_caddow': '50多岁成熟自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'fisher_bram': '60多岁老年热情精明的商人小贩，语速明快、亲切流畅的市井男性嗓音',
    'fisher_nell': '20多岁在海边惊魂未定的年轻渔妇，声音轻微颤抖、带着后怕与柔弱的年轻女性嗓音',
    'fisherman_brandt': '常年在海边抽烟斗、有点怪癖的粗犷老渔民口吻',
    'foreman_odell': '沙哑暴躁的矿工工头大嗓门，粗犷有力',
    'forgemistress_darva': '城镇铁匠铺女主管，粗犷刚毅、声音如击打玄铁般有力的成熟女性低中音',
    'fury': '30多岁自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'gardener_yew': '60多岁老年自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'gatecaptain_brannoc': '50多岁成熟威严刚毅的军人，低沉有力、沉稳干练的成年男性男中音',
    'gatewarden_pell': '30多岁自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'gravedigger_mosley': '战战兢兢、神情紧张的掘墓人口吻',
    'harbormaster_odile': '峭壁渔港的女港口长，饱经风霜海盐、爽朗干练的海港女主管嗓音',
    'head_gardener_amaranth': '守护古老花园十年的老女园丁，嗓音轻柔沙哑、略带疲惫与细致关怀的年长女性嗓音',
    'hearthkeeper_maeve': '极北温暖客栈的女老板娘，慈祥温厚、热情好客的成熟母亲女性嗓音',
    'herbalist_yara': '沼泽深处的神秘草药女巫，声音低沉沙哑、慢条斯理且深不可测的女性烟嗓',
    'hermit_okku': '50多岁成熟饱经沧桑的长者，声音沉稳和蔼、语调舒缓的中老年男性男低音',
    'heroic_quartermaster': '40多岁中年威严刚毅的军人，低沉有力、沉稳干练的成年男性男中音',
    'huntsman_deral': '40多岁中年自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'ignivar': '狂暴烈焰与熔炉巨兽魔神咆哮口吻，炽热低沉且充满毁灭压迫感',
    'keeper_bram': '60多岁老年粗犷硬朗的劳动工人，中气十足、声音洪亮有力的成年男性嗓音',
    'keeper_saelwyn': '30多岁从容干练的女性，自然沉稳、清晰流畅的女性中音',
    'lamplighter_sorrel': '40多岁中年自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'lampman_cobb': '60多岁老年饱经沧桑的长者，声音沉稳和蔼、语调舒缓的中老年男性男低音',
    'lira_dewsong': '清澈空灵、宛如夜莺的精灵女歌者嗓音',
    'loremaster_caddis': '50多岁成熟热情精明的商人小贩，语速明快、亲切流畅的市井男性嗓音',
    'loremother_bryn': '神社守护者老妇人，温和沧桑、慢条斯理如诵读经卷的年长女性嗓音',
    'marshal_redbrook': '50多岁饱经风霜的军团老元帅，沙哑低沉、刚毅如磐石的威严军人男低音',
    'mender_saul': '40多岁中年自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'mother_sedge': '慈祥神秘、深邃安详的沼泽老妇人女性嗓音',
    'netter_maris': '熟练的捕鳗女渔民，语速极快、热情唠叨且带着市井烟火气的女性嗓音',
    'nythraxis': '极度霸道低沉的古代暗黑君王巨龙咆哮口吻，古老威严且充满毁灭压迫感',
    'orchardist_pomeline': '看守古老果园的老妇人，声音酸甜干练、带有护食倔强的年长女性嗓音',
    'pearlmother_isha': '采珠部族的德高望重女族长，深沉从容、慈爱威严的年长母性嗓音',
    'provisioner_fenna': '30多岁自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'provisioner_hale': '40多岁中年热情精明的商人小贩，语速明快、亲切流畅的市井男性嗓音',
    'quartermaster_bree': '利落高效、有条不紊的女军需官口吻',
    'quartermaster_edda': '要塞军需女官，疲惫坚毅、雷厉风行的军旅女性嗓音',
    'quartermaster_sela': '物资军需女官，务实利落、略带疲倦的干练女性嗓音',
    'reeve_ottoline': '丰收镇女执政官，干练从容、略带威严幽默的年长女性嗓音',
    'riftwatch_ollun': '40多岁中年自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'salvage_boss_ryna': '豪迈坚毅、雷厉风行的打捞队女首领口吻',
    'salvager_edda': '沙滩拾荒沉船的女打捞者，干练冷峻、略带讥讽与世故的独行女性嗓音',
    'scout_einna': '常年在雪原巡逻的年轻女斥候，嗓音紧凑短促、冷静戒备的年轻女性嗓音',
    'scout_maren': '机警短促、压低嗓音的敏捷年轻女斥候口吻',
    'scout_yerrin': '在敌前哨岗独自潜伏一个月的女斥候，压低嗓音、极度敏锐警惕的女性低语嗓音',
    'sexton_marrow': '50多岁成熟饱经沧桑的长者，声音沉稳和蔼、语调舒缓的中老年男性男低音',
    'smith_haldren': '40多岁至50岁粗犷洪亮的铁匠大师，在熔炉旁中气十足、声音如钢铁般有力的男低音',
    'spirit_healer': '空灵神圣、超然物外的远古灵魂女医者语气',
    'stablemaster_marla': '干练爽朗、热情洋溢的马厩女老板口吻',
    'strandwatcher_pell': '30多岁自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'tanner_hesk': '40多岁中年自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'the_merchant': '50多岁精明能干的商会拍卖官，语调温润连贯、充满诱惑力与市井喜感的从容中年男中音',
    'tidewatcher_ondrel': '30多岁自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'tinker_gizzel': '30多岁自然沉稳的奇幻冒险者，语调清晰自然的中年男性男中音',
    'trader_wilkes': '40多岁热情洋溢的市井小贩，语速明快、带着爽朗笑意的亲切中年男高音',
    'trapper_brosk': '60多岁老年饱经沧桑的长者，声音沉稳和蔼、语调舒缓的中老年男性男低音',
    'varkhul': '古老苍劲、坚如磐石的终焉熔炉锻造之父，深沉浑厚的远古神明低音',
    'vicar_creel': '50多岁成熟热情精明的商人小贩，语速明快、亲切流畅的市井男性嗓音',
    'warden_coalfast': '40多岁中年威严刚毅的军人，低沉有力、沉稳干练的成年男性男中音',
    'warden_fenwick': '40多岁中年威严刚毅的军人，低沉有力、沉稳干练的成年男性男中音',
    'warden_kaldra': '冷峻坚决、忠诚警惕的女守望者口吻',
    'wardsmith_orun': '50多岁成熟饱经沧桑的长者，声音沉稳和蔼、语调舒缓的中老年男性男低音',
    'watcher_maren': '迎风山隘的女守卫者，声音高亢嘹亮、能在呼啸寒风中清晰传达命令的女性嗓音',
    'waykeeper_pell': '沼泽台阶上的客栈女看守，随和温厚、从容热情的成熟女性嗓音',
    'waywatcher_sorrel': '高山隘口的女守望者，嘹亮坚毅、在风中传颂警报的年轻女性嗓音',
    'weaver_amelle': '温和细致、耐心专注的纺织女工口吻',
    'weaver_ottilie': '纺织工坊的织造女大师，从容沉稳、字句优雅考究的成熟女性中音',
    'wickmother_sorrel': '乡村旅店的老板娘，热情忙碌、语调亲切朴实的年长妇人女性嗓音',
    'widow_tansy': '制作守灵烛的孤苦老妇人，声音苍老轻微颤抖、带着淡淡哀伤的年长女性嗓音',
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


def compute_fingerprint(text: str, instruct: str) -> str:
    """计算单条语音的配置指纹，用于变更检测"""
    h = hashlib.md5()
    h.update(text.encode('utf-8'))
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
        instruct = NPC_VOICE_INSTRUCTS.get(voice_npc, DEFAULT_INSTRUCT)
        fingerprint = compute_fingerprint(clean_text, instruct)
        
        catalog[line_key] = {
            "key": line_key,
            "voice_npc": voice_npc,
            "text": clean_text,
            "speaker": "(由 instruct 描述生成)",
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


def run_predict_with_timeout(client: Client, item: dict, timeout_sec: int = 240):
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
            res = run_predict_with_timeout(client, item, timeout_sec=240)
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
