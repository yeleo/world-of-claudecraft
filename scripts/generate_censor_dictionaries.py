#!/usr/bin/env python3
# ==============================================================================
# scripts/generate_censor_dictionaries.py
# Clean, synthesize, and generate production-grade censor dictionaries.
# Adheres strictly to the 64KB ceiling of USERNAME_BANLIST_FILE_MAX_BYTES.
# ==============================================================================

import os
import re
import unicodedata

BASE_DIR = '/home/yeleo/src/world-of-claudecraft'
SRC_DIR = os.path.join(BASE_DIR, 'scratch', 'censor_sources')
DATA_DIR = os.path.join(BASE_DIR, 'data', 'censor')

SAFE_WHITELIST = {
    # MMO Classes & Roles
    '战士', '法师', '牧师', '潜行者', '盗贼', '德鲁伊', '猎人', '圣骑士', '萨满', '术士', '死骑', '死亡骑士', '武僧', '恶魔猎手', '唤魔师',
    '坦克', '输出', '治疗', '防战', '狂暴战', '武器战', '火法', '冰法', '奥法', '神牧', '戒律牧', '暗牧', '奶骑', '惩戒骑', '防骑',
    '奶萨', '元素萨', '增强萨', '奶德', '野德', '鸟德', '熊德', '兽王猎', '射击猎', '生存猎', '刺杀贼', '狂徒贼', '敏锐贼',
    # Combat & Stats
    '暴击', '急速', '精通', '全能', '命中', '防御', '格挡', '招架', '闪避', '护甲', '抗性', '穿透', '韧性', '吸血',
    '力量', '敏捷', '智力', '耐力', '精神', '生命值', '法力值', '能量', '怒气', '符文', '集中值', '圣能',
    '伤害', '秒伤', '治疗量', '减伤', '免伤', '仇恨', '嘲讽', '控制', '打断', '驱散', '净化', '复活', '战复',
    # Gameplay Systems
    '技能', '天赋', '天赋树', '雕文', '铭文', '专精', '姿态', '光环', '图腾', '祝福', '印记', '诅咒', '陷阱',
    '副本', '地下城', '团队副本', '团本', '首领', '精英', '小怪', '掉落', '拾取', '分配', '黑本', '灭团', '开荒', '伐木',
    '日常', '周常', '任务', '主线', '支线', '剧情', '成就', '头衔', '坐骑', '宠物', '幻化', '玩具',
    '操作', '手法', '走位', '跑位', '拉怪', '聚怪', '控怪', '集火', '转火', '爆发', '平砍', '读条', '瞬发', '引导',
    '背包', '行囊', '行囊整理', '银行', '公会银行', '仓库', '邮件', '信件', '邮箱', '包裹',
    '草药', '采草', '百草', '草药学', '采矿', '挖矿', '锻造', '工程', '工程学', '裁缝', '炼金', '炼金术', '附魔', '剥皮', '制皮', '烹饪', '钓鱼', '急救',
    # Social & Economy
    '公会', '工会', '公会会长', '官员', '会员', '团队', '队伍', '小队', '进组', '入队', '退组', '离队', '组人', '求组', '开组',
    '交易', '商行', '拍卖行', '拍卖', '竞标', '一口价', '金币', '银币', '铜币', '代币', '荣誉点', '征服点',
    '频道', '综合', '综合频道', '世界频道', '公会频道', '队伍频道', '团队频道', '说', '大喊', '密语', '私聊',
    '好友', '黑名单', '屏蔽', '举报', '组队查找器', '集合石',
    # Lore & World
    '联盟', '部落', '暴风城', '奥格瑞玛', '幽暗城', '达纳苏斯', '铁炉堡', '雷霆崖', '银月城', '埃索达',
    '艾泽拉斯', '卡利姆多', '东部王国', '外域', '诺森德', '潘达利亚', '魔兽', '魔兽世界', '克劳德', '克劳德工艺',
    '人类', '兽人', '矮人', '暗夜精灵', '亡灵', '牛头人', '侏儒', '巨魔', '血精灵', '德莱尼', '地精', '狼人', '熊猫人',
    # Engine & Network
    '网络', '网速', '延迟', '卡顿', '掉线', '掉线了', '断线', '重连', '连接', '登录', '登出', '退出', '注册', '账号', '角色',
    '服务器', '区服', '维护', '更新', '补丁', '客户端', '帧率', '画质', '分辨率', '全屏', '窗口', '设置', '声音', '音乐',
    '管理员', '系统消息', '系统公告', '防沉迷', '实名认证', '健康游戏', '适龄提示', '用户协议', '隐私政策',
    # Gear
    '装备', '武器', '防具', '头盔', '肩膀', '胸甲', '护腕', '手套', '腰带', '护腿', '靴子', '项链', '戒指', '饰品', '披风',
    '主手', '副手', '双手', '单手', '远程', '盾牌', '法杖', '长柄武器', '单手剑', '双手剑', '单手斧', '双手斧', '单手锤', '双手锤', '匕首', '弓', '弩', '枪械',
    '魔杖', '投掷武器', '布甲', '皮甲', '锁甲', '板甲',
    '升级', '满级', '经验', '经验值', '升级了', '声望', '崇拜', '崇敬', '尊敬', '友善', '中立', '敌对', '仇恨',
    # Everyday Benign Words (Avoid Scunthorpe Collisions)
    '中国', '中华', '国家', '人民', '社会', '大家', '朋友', '兄弟', '姐妹', '同学', '老师', '父母', '爸爸', '妈妈', '孩子',
    '自由', '民主', '文明', '和谐', '爱国', '敬业', '诚信', '友善', '富强', '平等', '公正', '法治',
    '工作', '学习', '生活', '兼职', '招聘', '求职', '考试', '大学', '学校', '公司', '平台', '平台服务',
    '开心', '快乐', '高兴', '舒服', '难过', '伤心', '厉害', '牛逼', '牛批', '不错', '可以', '很好', '谢谢', '不客气', '再见', '晚安',
    '戍边', '边疆', '边防', '英雄', '烈士', '和平', '安全', '合法', '合规', '正常', '测试', '交流', '分享', '讨论', '退出团队'
}

def clean_term(w):
    if not w:
        return ''
    w = unicodedata.normalize('NFKC', w).strip()
    w = re.sub(r'^[\s\-_.,;:!?#*~`@$%^&+=/\\|\[\]{}()<>]+|[\s\-_.,;:!?#*~`@$%^&+=/\\|\[\]{}()<>]+$', '', w)
    return w

def is_valid_term(w):
    if not w:
        return False
    has_cjk = bool(re.search(r'[\u4e00-\u9fa5]', w))
    if has_cjk:
        cjk_count = len(re.findall(r'[\u4e00-\u9fa5]', w))
        if cjk_count < 2 and len(w) < 3:
            return False
    else:
        if len(w) < 3 or re.match(r'^[0-9]+$', w):
            return False
    if w in SAFE_WHITELIST:
        return False
    if re.search(r'\.(txt|jpg|png|gif|rar|zip|exe|7z|html|php|asp|mp4|avi)$', w, re.IGNORECASE):
        return False
    if re.search(r'^(http|https|www|ftp):', w, re.IGNORECASE):
        return False
    digits = re.findall(r'\d', w)
    if len(digits) >= 5 and len(digits) / len(w) > 0.4:
        return False
    if len(w) > 16:
        return False
    return True

def generate():
    hard_categories = {
        'cheats': set(),
        'politics': set(),
        'weapons_terror': set(),
        'drugs': set(),
        'blackmarket_fraud': set()
    }
    soft_set = set()

    # 1. Existing Hard
    existing_hard = os.path.join(DATA_DIR, 'censor_hard.txt')
    if os.path.exists(existing_hard):
        with open(existing_hard, 'r', encoding='utf-8') as f:
            for line in f:
                w = clean_term(line.split('#')[0])
                if is_valid_term(w):
                    hard_categories['cheats'].add(w)

    # 2. Existing Soft
    existing_soft = os.path.join(DATA_DIR, 'censor_soft.txt')
    if os.path.exists(existing_soft):
        with open(existing_soft, 'r', encoding='utf-8') as f:
            for line in f:
                w = clean_term(line.split('#')[0])
                if is_valid_term(w):
                    soft_set.add(w)

    # 3. Konsheng Sources
    for fname, cat in [('konsheng_guns.txt', 'weapons_terror'), ('konsheng_violence.txt', 'weapons_terror'),
                       ('konsheng_politics.txt', 'politics'), ('konsheng_rebellion.txt', 'politics')]:
        p = os.path.join(SRC_DIR, fname)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    w = clean_term(line)
                    if is_valid_term(w):
                        hard_categories[cat].add(w)

    for fname in ['konsheng_porn.txt', 'konsheng_ads.txt']:
        p = os.path.join(SRC_DIR, fname)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    w = clean_term(line)
                    if is_valid_term(w):
                        soft_set.add(w)

    # 4. Houbb Tags
    tag_path = os.path.join(SRC_DIR, 'houbb_tags.txt')
    if os.path.exists(tag_path):
        with open(tag_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                w = clean_term(parts[0])
                if not is_valid_term(w):
                    continue
                tags = parts[1].split(',') if len(parts) > 1 else []
                if '0' in tags:
                    if len(hard_categories['politics']) < 1200:
                        hard_categories['politics'].add(w)
                elif '1' in tags:
                    if any(k in w for k in ['毒品', '海洛因', '冰毒', '麻古', '摇头丸', 'k粉', 'K粉', '大麻', '迷药', '三唑仑', '杜冷丁', '可卡因', '致幻', '鸦片', '吸毒', '贩毒']):
                        if len(hard_categories['drugs']) < 600:
                            hard_categories['drugs'].add(w)
                elif '4' in tags:
                    if any(k in w for k in ['外挂', '私服', '自瞄', '透视', '锁血', '秒杀', '脱机', '买枪', '手枪', '步枪', '雷管', '炸药', '黑火药', '自杀', '买凶', '杀人', '代考', '假钞', '洗钱', '黑卡', '封包']):
                        if len(hard_categories['weapons_terror']) < 1200:
                            hard_categories['weapons_terror'].add(w)
                if '2' in tags or '3' in tags:
                    soft_set.add(w)

    # 5. Netease & Tencent Sources
    for fname in ['netease.txt', 'tencent.txt']:
        p = os.path.join(SRC_DIR, fname)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    w = clean_term(line)
                    if is_valid_term(w) and any(k in w for k in ['逼', '操', '日你', '干你', '妈', '爹', '爷', '贱', '骚', '蠢', '笨', '猪', '狗', '死', '杂种', '煞笔', '傻', '混蛋', '蛋', '滚', '屁']):
                        soft_set.add(w)

    all_hard = set()
    for cat in hard_categories:
        all_hard.update(hard_categories[cat])

    soft_set = soft_set - all_hard

    # Write Hard
    hard_path = os.path.join(DATA_DIR, 'censor_hard.txt')
    lines = [
        '# ==============================================================================',
        '# World of Claudecraft - 硬词库 (Hard Filter - 服务端强制拦截 + 惩罚禁言 + 创角禁名)',
        '# ==============================================================================',
        ''
    ]
    for cat, title in [
        ('cheats', '# --- 1. 外挂、辅助工具与私服作弊黑产 (游戏核心命脉) ---'),
        ('politics', '# --- 2. 政治红线、涉政违规与反动分裂言论 (法定底线) ---'),
        ('weapons_terror', '# --- 3. 枪支弹药、危化品暴恐与严重违法犯罪 ---'),
        ('drugs', '# --- 4. 涉毒、违禁精神药物与化学毒品 ---'),
        ('blackmarket_fraud', '# --- 5. 账号交易黑卡代充与地下洗钱欺诈 ---')
    ]:
        lines.append(title)
        for w in sorted(list(hard_categories[cat])):
            lines.append(w)
        lines.append('')

    with open(hard_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    hard_size = os.path.getsize(hard_path)
    print(f'Wrote {hard_path}: {len(all_hard)} words, {hard_size} bytes ({hard_size/1024:.2f} KB)')
    assert hard_size < 65536, f'Error: {hard_path} size {hard_size} exceeds 64KB ceiling!'

    # Write Soft
    soft_path = os.path.join(DATA_DIR, 'censor_soft.txt')
    soft_lines = [
        '# ==============================================================================',
        '# World of Claudecraft - 软词库 (Soft Filter - 客户端/服务端星号遮蔽，不惩罚)',
        '# ==============================================================================',
        ''
    ]
    for w in sorted(list(soft_set)):
        soft_lines.append(w)

    with open(soft_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(soft_lines))
    soft_size = os.path.getsize(soft_path)
    print(f'Wrote {soft_path}: {len(soft_set)} words, {soft_size} bytes ({soft_size/1024:.2f} KB)')

    # Write Whitelist
    whitelist_path = os.path.join(DATA_DIR, 'censor_whitelist.txt')
    wl_lines = [
        '# ==============================================================================',
        '# World of Claudecraft - 业务免死白名单 (Safe Whitelist - 严防误杀)',
        '# ==============================================================================',
        ''
    ]
    for w in sorted(list(SAFE_WHITELIST)):
        wl_lines.append(w)
    with open(whitelist_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(wl_lines))
    print(f'Wrote {whitelist_path}: {len(SAFE_WHITELIST)} words')

    # Copy script to scripts/
    target_script = os.path.join(BASE_DIR, 'scripts', 'generate_censor_dictionaries.py')
    with open(__file__, 'r', encoding='utf-8') as sf, open(target_script, 'w', encoding='utf-8') as df:
        df.write(sf.read())
    os.chmod(target_script, 0o755)
    print(f'Synced self to {target_script}')

if __name__ == '__main__':
    generate()
