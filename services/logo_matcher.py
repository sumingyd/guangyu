import os
import re
from typing import Optional, List, Tuple, Callable, Union, Set, Dict
from re import Pattern
from difflib import SequenceMatcher

LogoRule = Tuple[Pattern, Union[str, Callable[[re.Match], Optional[str]]]]


class LogoMatcher:

    LOGO_BASE_URL = 'https://raw.githubusercontent.com/sumingyd/guangyu/main/img/'

    # ── 所有可用 logo 文件名（不含 .png 后缀） ──
    # 新增 logo 后需运行: (Get-ChildItem img/*.png -Name) | ForEach-Object { "'$($_ -replace '\.png$','')'," } | Sort-Object
    _AVAILABLE_LOGOS: Set[str] = frozenset({
        '阿里郎', '爱上4K', '安徽卫视', '安丘', '安丘民生', '安丘综合', '安阳', '安阳科教',
        '安阳文旅', '安阳新闻综合', '澳门电视台', '宝丰', '北京卫视', '北京卫视4K', '滨州',
        '滨州民生', '滨州综合', '兵团卫视', '博兴', '博兴综合', '财富天下', '茶频道',
        '昌乐综合', '昌邑综合', '常州都市', '常州金坛电视台', '常州生活', '常州文化公共',
        '常州新闻', '车迷频道', '城市剧场', '茌平综合', '重庆卫视', '纯享4K', '哒啵电竞',
        '岱岳', '岱岳综合', '单县综合', '郸城', '德州生活', '德州综合', '登封', '邓州',
        '邓州电视台', '谍战剧场', '定陶综合', '东阿综合', '东昌综合', '东方财经', '东方卫视',
        '东方卫视4K', '东海新闻', '东明综合', '东南卫视', '东平', '东平综合', '东营公共',
        '东营综合', '动漫秀场', '动作影院', '都市剧场', '多彩文体4K', '发现之旅', '法兰西',
        '法治天地', '范县', '方城', '肥城综合', '翡翠剧集台', '封丘', '凤凰卫视', '凤凰香港',
        '凤凰中文', '凤凰资讯', '扶沟', '甘肃卫视', '甘肃卫视1', '甘肃卫视3', '赣榆', '高淳',
        '高密综合', '高青综合', '巩义', '古装剧场', '固始', '冠县综合', '光山', '广东体育',
        '广东卫视', '广东卫视4K', '广饶综合', '广西卫视', '贵州卫视', '哈哈炫动', '海南卫视',
        '海阳', '海阳综合', '海阳综艺', '海洋频道', '好学生', '河北卫视', '河东综合', '河南卫视',
        '菏泽公共', '菏泽综合', '鹤壁', '鹤壁新闻综合', '黑龙江卫视', '黑莓电影', '黑莓动画',
        '红色影视', '湖北卫视', '湖南卫视', '湖南卫视4K', '华数', '滑县', '淮安公共',
        '淮安新闻综合', '淮安影视娱乐', '淮滨', '淮阴综合', '欢笑剧场4K', '环球旅游',
        '桓台综合', '黄岛生活', '黄岛综合', '潢川', '辉县', '辉县电视台', '惠民综合', '获嘉',
        '吉林卫视', '即墨综合', '纪实科教', '济南都市', '济南教育', '济南科教', '济南鲁中',
        '济南少儿', '济南生活', '济南体育', '济南新闻', '济南娱乐', '济南综合', '济宁高新',
        '济宁公共', '济宁生活', '济宁综合', '济阳影视', '济阳综合', '济源', '家庭理财',
        '家庭影院', '嘉佳卡通', '嘉祥综合', '郏县', '贾汪新闻', '建安', '江苏城市', '江苏国际',
        '江苏教育', '江苏体育休闲', '江苏卫视', '江苏卫视4K', '江苏新闻', '江苏影视',
        '江苏综艺', '江西卫视', '胶州综合', '焦作', '焦作电视台', '焦作公共', '焦作文旅',
        '焦作综合', '金色学堂', '金鹰纪实', '金鹰卡通', '经典剧场', '睛彩广场舞', '睛彩竞技',
        '睛彩篮球', '睛彩青少', '精彩影视', '九屏同看', '居家购物', '莒南综合', '莒县综合',
        '巨野综合', '鄄城综合', '军旅剧场', '浚县', '卡酷少儿', '开封', '开封文化旅游',
        '开封新闻综合', '快乐垂钓', '莱西综合', '兰考', '兰陵公共', '兰陵综合', '岚山综合',
        '崂山综合', '乐游', '梨园频道', '历城综合', '连云港公共', '连云港生活频道',
        '连云港新闻综合', '梁山综合', '辽宁卫视', '聊城民生', '聊城综合', '林州', '临清综合',
        '临朐综合', '临沭综合', '临邑综合', '临颍', '临淄综合', '陵城综合', '龙口综合',
        '卢氏', '鹿邑', '栾川', '罗山', '洛宁', '洛阳电视台', '洛阳科教', '洛阳文旅',
        '洛阳新闻综合', '漯河', '漯河新闻综合', '魅力足球', '蒙阴综合', '孟津', '孟州',
        '咪咕影院', '咪视界', '渑池', '牟平生活', '牟平综合', '南京教科频道', '南京少儿',
        '南京生活', '南京十八', '南京文旅纪录', '南京新闻综合', '南通', '南通-2台', '南通1台',
        '南通2台', '南通3台', '南通公共崇川', '南通新闻综合', '南阳', '南阳公共', '南阳科教',
        '南阳图文', '南阳新闻综合', '内黄', '内蒙古卫视', '内乡', '宁津综合', '宁夏卫视',
        '宁阳', '宁阳生活', '宁阳综合', '农林卫视', '欧洲新闻', '沛县综合', '蓬莱综合',
        '邳州', '平顶山', '平顶山城市', '平顶山电视台', '平顶山公共', '平顶山教育',
        '平顶山新闻综合', '平度综合', '平阴综合', '平原综合', '濮阳', '濮阳公共', '濮阳县',
        '濮阳新闻综合', '栖霞综合', '齐河综合', '淇县', '杞县', '汽摩', '沁阳', '沁阳1',
        '青海卫视', '青州文旅', '青州综合', '清丰', '求索动物', '求索纪录', '求索科学',
        '求索生活', '曲阜综合', '确山', '任城生活', '任城综合', '日照', '日照公共', '日照科教',
        '日照综合', '荣成综合', '汝南', '汝阳', '汝州', '乳山综合', '三门峡', '三门峡新闻综合',
        '三沙卫视', '厦门卫视', '山东交通广播', '山东教育卫视', '山东经济广播', '山东农科',
        '山东齐鲁', '山东少儿', '山东生活', '山东体育', '山东卫视', '山东卫视4', '山东卫视4K',
        '山东文旅', '山东新闻', '山东综合广播', '山东综艺', '山亭综合', '山西卫视', '陕西卫视',
        '商城', '商河综合', '商丘', '商丘公共', '商丘文体科教', '商丘新闻综合', '上蔡', '上街',
        '射阳新闻综合', '莘县综合', '深圳卫视', '深圳卫视4K', '沈丘', '生活时尚', '生态环境',
        '市中综合', '寿光蔬菜', '寿光综合', '书画', '沭阳综合', '四川卫视', '四川卫视1',
        '四川卫视4K', '四海钓鱼', '泗洪综合', '泗水', '泗水综合', '泗阳综合', '嵩县', '苏超1',
        '苏超联赛', '苏州生活资讯', '苏州新闻综合5', '宿迁', '宿迁新闻综合', '宿豫综合',
        '睢宁', '遂平', '台儿庄综合', '台前县', '太康', '泰安经济生活', '泰安综合', '泰山综合',
        '泰兴综合', '泰州2台', '泰州3台', '泰州新闻综合', '汤阴', '唐河', '滕州综合', '天津卫视',
        '天下足球', '通许', '铜山1', '威海生活', '威海综合', '微山', '微山综合', '潍坊高新',
        '潍坊公共', '潍坊科教', '潍坊生活', '潍坊综合', '卫辉', '尉氏', '温县', '文登生活',
        '文登综合', '文旅记录', '文物宝库', '汶上综合', '无棣综合', '无锡都市资讯',
        '无锡新闻综合', '五莲综合', '武城影视', '武城综合', '武术世界', '武陟', '舞钢',
        '舞钢电视台', '舞阳', '西藏卫视', '西华', '西平', '夏津公共', '夏津综合', '夏邑',
        '夏邑电视台', '先锋乒羽', '襄城', '祥符', '响水综合', '项城', '新安', '新蔡', '新动漫',
        '新加坡新闻', '新疆卫视', '新密', '新密电视台', '新视觉', '新泰乡村', '新泰综合',
        '新县', '新乡', '新乡公共', '新乡县', '新乡新闻综合', '新野', '新沂1台', '新郑',
        '信阳', '信阳教育', '信阳文旅', '信阳新闻综合', '星空国际', '荥阳', '兴化新闻综合',
        '盱眙综合', '徐州1台', '徐州2台', '徐州3台', '徐州沛县新闻综合', '徐州新闻综合',
        '许昌', '许昌农业科教', '许昌综合', '薛城综合', '烟台', '烟台公共', '烟台经济',
        '烟台影视', '烟台综合', '鄢陵', '延边卫视', '盐城新闻综合', '兖州综合', '偃师',
        '央广购物', '扬州新闻综合', '阳信综合', '叶县', '伊川', '沂南综合', '沂水生活',
        '沂水综合', '沂源综合', '宜阳', '义马', '峄城综合', '永城', '优漫卡通', '优优宝贝',
        '游戏风云', '鱼台生活', '鱼台综合', '虞城', '禹城综合', '禹城综艺', '禹州', '原阳',
        '云南卫视', '郓城综合', '沾化综合', '张店综合', '章丘综合', '长岛综合', '长清综合',
        '长垣', '招远综合', '浙江卫视', '浙江卫视4K', '镇江', '镇江新闻综合', '镇平', '正阳',
        '郑州电视台', '郑州都市生活', '郑州妇女儿童', '郑州教育', '郑州商都频道', '郑州文体旅游',
        '郑州新闻综合', '郑州豫剧频道', '至臻视界4K', '中国交通', '中国天气', '中华特产',
        '中学生', '重温经典', '重温经典影视', '周村综合', '周口', '周口新闻综合', '诸城综合',
        '驻马店', '驻马店公共', '驻马店科教', '驻马店台', '驻马店新闻综合', '淄博民生',
        '淄博文旅', '淄博影视', '淄博综合', '淄川综合', '邹城综合', '邹平综合',
        'CCTV1', 'CCTV2', 'CCTV3', 'CCTV4', 'CCTV4K', 'CCTV4欧洲', 'CCTV4美洲',
        'CCTV5', 'CCTV5+', 'CCTV6', 'CCTV7', 'CCTV8', 'CCTV9', 'CCTV10', 'CCTV11',
        'CCTV12', 'CCTV13', 'CCTV14', 'CCTV15', 'CCTV16', 'CCTV16五环', 'CCTV17',
        'CCTV兵器科技', 'CCTV风云剧场', 'CCTV风云音乐', 'CCTV风云足球', 'CCTV高尔夫网球',
        'CCTV怀旧剧场', 'CCTV女性时尚', 'CCTV世界地理', 'CCTV卫生健康', 'CCTV央视台球',
        'CCTV央视文化精品', 'CCTV中视购物',
        'CETV1', 'CETV2', 'CETV3', 'CETV4',
        'CGTN', 'CGTN阿语', 'CGTN俄语', 'CGTN法语', 'CGTN纪录', 'CGTN西语',
        'CHC动作电影', 'CHC高清电影', 'CHC家庭影院', 'CHC影迷电影',
        'cna', 'DW德国之声', 'NHK世界台',
        'QTV1', 'QTV2', 'QTV3', 'QTV4', 'QTV5',
    })

    # ── 频道名中需要去除的画质后缀 ──
    _QUALITY_SUFFIXES: Tuple[str, ...] = (
        '超高清', '高清', 'HD', 'hd', 'Hd', '超清', '4K', '4k', '8K', '8k',
        '1080P', '1080p', '1080I', '1080i', '720P', '720p',
        'FHD', 'UHD', 'H265', 'H.265', 'HEVC', 'hevc',
        '原画', '蓝光', '无台标', '纯净', '标清', '流畅',
    )

    # ── 频道名中需要去除的通用后缀（按长度降序排列） ──
    _GENERIC_SUFFIXES: Tuple[str, ...] = (
        '广播电视台', '电视台', '卫视台', '频道', '电视', '卫视',
    )

    # 特殊字符（括号、标记等）
    _SPECIAL_CHARS_RE = re.compile(r'[()（）\[\]【】{}<>《》\*×]')

    # 分隔符（用于创建紧凑版本）
    _SEPARATOR_RE = re.compile(r'[-_.\s]+')

    def __init__(self, base_url: Optional[str] = None):
        self.base_url: str = base_url if base_url is not None else self.LOGO_BASE_URL
        self.rules: List[LogoRule] = self._build_rules()

        # 构建查找用的数据结构
        # 排除 "已停用"
        clean_logos = {s for s in self._AVAILABLE_LOGOS if s and s != '已停用'}
        # 按长度降序排列（优先匹配更长的名称）
        self._logo_stems_sorted: List[str] = sorted(clean_logos, key=len, reverse=True)
        # 小写名称到原始名称的映射（用于精确匹配）
        self._logo_map: Dict[str, str] = {s.lower(): s for s in clean_logos}
        # 紧凑版本（去除分隔符）的映射
        self._logo_compact_map: Dict[str, str] = {}
        for s in clean_logos:
            compact = self._SEPARATOR_RE.sub('', s).lower()
            if compact and compact not in self._logo_compact_map:
                self._logo_compact_map[compact] = s

    def _build_rules(self) -> List[LogoRule]:
        rules: List[LogoRule] = []

        rules.extend([
            (re.compile(r'^CCTV5\+', re.IGNORECASE), 'CCTV5+.png'),
            (re.compile(r'^CCTV4K', re.IGNORECASE), 'CCTV4K.png'),
            (re.compile(r'^CCTV16五环', re.IGNORECASE), 'CCTV16五环.png'),
            (re.compile(r'^CCTV16', re.IGNORECASE), 'CCTV16.png'),
            (re.compile(r'^CCTV4欧洲', re.IGNORECASE), 'CCTV4欧洲.png'),
            (re.compile(r'^CCTV4美洲', re.IGNORECASE), 'CCTV4美洲.png'),
            (re.compile(r'^CCTV中视购物', re.IGNORECASE), 'CCTV中视购物.png'),
            (re.compile(r'^CCTV(\d+)', re.IGNORECASE), lambda m: f'CCTV{m.group(1)}.png'),
        ])

        rules.extend([
            (re.compile(r'^CGTN俄语'), 'CGTN俄语.png'),
            (re.compile(r'^CGTN法语'), 'CGTN法语.png'),
            (re.compile(r'^CGTN阿语'), 'CGTN阿语.png'),
            (re.compile(r'^CGTN西语'), 'CGTN西语.png'),
            (re.compile(r'^CGTN纪录'), 'CGTN纪录.png'),
            (re.compile(r'^CGTN'), 'CGTN.png'),
        ])

        rules.extend([
            (re.compile(r'^CETV1', re.IGNORECASE), 'CETV1.png'),
            (re.compile(r'^CETV2', re.IGNORECASE), 'CETV2.png'),
            (re.compile(r'^CETV3', re.IGNORECASE), 'CETV3.png'),
            (re.compile(r'^CETV4', re.IGNORECASE), 'CETV4.png'),
            (re.compile(r'^中国教育1'), 'CETV1.png'),
            (re.compile(r'^中国教育2'), 'CETV2.png'),
            (re.compile(r'^中国教育4'), 'CETV4.png'),
        ])

        rules.extend([
            (re.compile(r'^QTV(\d+)', re.IGNORECASE), lambda m: f'QTV{m.group(1)}.png'),
        ])

        satellite_4k = [
            '北京卫视', '东方卫视', '湖南卫视', '浙江卫视', '江苏卫视',
            '广东卫视', '深圳卫视', '山东卫视', '四川卫视',
        ]
        for name in satellite_4k:
            rules.append((re.compile(f'^{name}4K'), f'{name}4K.png'))

        satellite_logos = [
            '北京卫视', '东方卫视', '湖南卫视', '浙江卫视', '江苏卫视',
            '广东卫视', '深圳卫视', '山东卫视', '四川卫视', '天津卫视',
            '重庆卫视', '河北卫视', '河南卫视', '湖北卫视', '安徽卫视',
            '江西卫视', '辽宁卫视', '黑龙江卫视', '吉林卫视', '云南卫视',
            '贵州卫视', '陕西卫视', '山西卫视', '广西卫视', '新疆卫视',
            '内蒙古卫视', '宁夏卫视', '西藏卫视', '青海卫视', '海南卫视',
            '甘肃卫视', '东南卫视', '农林卫视', '厦门卫视', '延边卫视',
            '三沙卫视', '兵团卫视',
        ]
        for name in satellite_logos:
            rules.append((re.compile(f'^{name}'), f'{name}.png'))

        rules.append((re.compile(r'^(.{2,3})卫视'), lambda m: f'{m.group(1)}卫视.png'))

        rules.extend([
            (re.compile(r'^凤凰中文'), '凤凰中文.png'),
            (re.compile(r'^凤凰资讯'), '凤凰资讯.png'),
            (re.compile(r'^凤凰香港'), '凤凰香港.png'),
            (re.compile(r'^凤凰卫视'), '凤凰卫视.png'),
        ])

        rules.extend([
            (re.compile(r'^澳门'), '澳门电视台.png'),
            (re.compile(r'^澳视'), '澳门电视台.png'),
            (re.compile(r'^澳亚'), '澳门电视台.png'),
        ])

        rules.extend([
            (re.compile(r'^风云音乐'), 'CCTV风云音乐.png'),
            (re.compile(r'^风云足球'), 'CCTV风云足球.png'),
            (re.compile(r'^风云剧场'), 'CCTV风云剧场.png'),
            (re.compile(r'^兵器科技'), 'CCTV兵器科技.png'),
            (re.compile(r'^怀旧剧场'), 'CCTV怀旧剧场.png'),
            (re.compile(r'^女性时尚'), 'CCTV女性时尚.png'),
            (re.compile(r'^世界地理'), 'CCTV世界地理.png'),
            (re.compile(r'^卫生健康'), 'CCTV卫生健康.png'),
            (re.compile(r'^央视台球'), 'CCTV央视台球.png'),
            (re.compile(r'^央视文化精品'), 'CCTV央视文化精品.png'),
            (re.compile(r'^高尔夫网球'), 'CCTV高尔夫网球.png'),
            (re.compile(r'^国防军事'), 'CCTV7.png'),
            (re.compile(r'^奥林匹克'), 'CCTV16.png'),
            (re.compile(r'^五环'), 'CCTV16五环.png'),
            (re.compile(r'^农业农村'), 'CCTV17.png'),
            (re.compile(r'^体育赛事'), 'CCTV5+.png'),
            (re.compile(r'^发现之旅'), '发现之旅.png'),
            (re.compile(r'^中学生'), '中学生.png'),
        ])

        rules.extend([
            (re.compile(r'^CHC动作电影'), 'CHC动作电影.png'),
            (re.compile(r'^CHC高清电影'), 'CHC高清电影.png'),
            (re.compile(r'^CHC家庭影院'), 'CHC家庭影院.png'),
            (re.compile(r'^CHC影迷电影'), 'CHC影迷电影.png'),
            (re.compile(r'^CHC'), 'CHC高清电影.png'),
        ])

        rules.extend([
            (re.compile(r'^家庭影院'), '家庭影院.png'),
            (re.compile(r'^咪咕影院'), '咪咕影院.png'),
            (re.compile(r'^咪视界'), '咪视界.png'),
            (re.compile(r'^爱上4K'), '爱上4K.png'),
            (re.compile(r'^纯享4K'), '纯享4K.png'),
            (re.compile(r'^多彩文体4K'), '多彩文体4K.png'),
            (re.compile(r'^至臻视界4K'), '至臻视界4K.png'),
            (re.compile(r'^欢笑剧场4K'), '欢笑剧场4K.png'),
        ])

        rules.extend([
            (re.compile(r'^中华特产'), '中华特产.png'),
            (re.compile(r'^中国交通'), '中国交通.png'),
            (re.compile(r'^中国天气'), '中国天气.png'),
            (re.compile(r'^书画'), '书画.png'),
            (re.compile(r'^优漫卡通'), '优漫卡通.png'),
            (re.compile(r'^优优宝贝'), '优优宝贝.png'),
            (re.compile(r'^先锋乒羽'), '先锋乒羽.png'),
            (re.compile(r'^军旅剧场'), '军旅剧场.png'),
            (re.compile(r'^动作影院'), '动作影院.png'),
            (re.compile(r'^动漫秀场'), '动漫秀场.png'),
            (re.compile(r'^卡酷少儿'), '卡酷少儿.png'),
            (re.compile(r'^古装剧场'), '古装剧场.png'),
            (re.compile(r'^嘉佳卡通'), '嘉佳卡通.png'),
            (re.compile(r'^哈哈炫动'), '哈哈炫动.png'),
            (re.compile(r'^四海钓鱼'), '四海钓鱼.png'),
            (re.compile(r'^城市剧场'), '城市剧场.png'),
            (re.compile(r'^家庭理财'), '家庭理财.png'),
            (re.compile(r'^快乐垂钓'), '快乐垂钓.png'),
            (re.compile(r'^新动漫'), '新动漫.png'),
            (re.compile(r'^新视觉'), '新视觉.png'),
            (re.compile(r'^武术世界'), '武术世界.png'),
            (re.compile(r'^求索纪录'), '求索纪录.png'),
            (re.compile(r'^求索动物'), '求索动物.png'),
            (re.compile(r'^求索科学'), '求索科学.png'),
            (re.compile(r'^求索生活'), '求索生活.png'),
            (re.compile(r'^汽摩'), '汽摩.png'),
            (re.compile(r'^法治天地'), '法治天地.png'),
            (re.compile(r'^游戏风云'), '游戏风云.png'),
            (re.compile(r'^环球旅游'), '环球旅游.png'),
            (re.compile(r'^生态环境'), '生态环境.png'),
            (re.compile(r'^生活时尚'), '生活时尚.png'),
            (re.compile(r'^精彩影视'), '精彩影视.png'),
            (re.compile(r'^红色影视'), '红色影视.png'),
            (re.compile(r'^红色影院'), '红色影视.png'),
            (re.compile(r'^经典剧场'), '经典剧场.png'),
            (re.compile(r'^谍战剧场'), '谍战剧场.png'),
            (re.compile(r'^都市剧场'), '都市剧场.png'),
            (re.compile(r'^重温经典影视'), '重温经典影视.png'),
            (re.compile(r'^重温经典'), '重温经典.png'),
            (re.compile(r'^金色学堂'), '金色学堂.png'),
            (re.compile(r'^金鹰卡通'), '金鹰卡通.png'),
            (re.compile(r'^金鹰纪实'), '金鹰纪实.png'),
            (re.compile(r'^魅力足球'), '魅力足球.png'),
            (re.compile(r'^天下足球'), '天下足球.png'),
            (re.compile(r'^睛彩广场舞'), '睛彩广场舞.png'),
            (re.compile(r'^睛彩竞技'), '睛彩竞技.png'),
            (re.compile(r'^睛彩篮球'), '睛彩篮球.png'),
            (re.compile(r'^睛彩青少'), '睛彩青少.png'),
            (re.compile(r'^纪实科教'), '纪实科教.png'),
            (re.compile(r'^乐游'), '乐游.png'),
            (re.compile(r'^东方财经'), '东方财经.png'),
            (re.compile(r'^广东体育'), '广东体育.png'),
            (re.compile(r'^梨园'), '梨园频道.png'),
            (re.compile(r'^九屏同看'), '九屏同看.png'),
            (re.compile(r'^华数'), '华数.png'),
            (re.compile(r'^央广购物'), '央广购物.png'),
            (re.compile(r'^哒啵电竞'), '哒啵电竞.png'),
            (re.compile(r'^翡翠剧集台'), '翡翠剧集台.png'),
            (re.compile(r'^财富天下'), '财富天下.png'),
            (re.compile(r'^茶频道'), '茶频道.png'),
            (re.compile(r'^车迷频道'), '车迷频道.png'),
            (re.compile(r'^文物宝库'), '文物宝库.png'),
            (re.compile(r'^黑莓电影'), '黑莓电影.png'),
            (re.compile(r'^黑莓动画'), '黑莓动画.png'),
            (re.compile(r'^DW德国之声'), 'DW德国之声.png'),
            (re.compile(r'^NHK世界台'), 'NHK世界台.png'),
        ])

        rules.extend([
            (re.compile(r'^山东教育卫视'), '山东教育卫视.png'),
            (re.compile(r'^山东交通广播'), '山东交通广播.png'),
            (re.compile(r'^山东经济广播'), '山东经济广播.png'),
            (re.compile(r'^山东综合广播'), '山东综合广播.png'),
            (re.compile(r'^山东农科'), '山东农科.png'),
            (re.compile(r'^山东齐鲁'), '山东齐鲁.png'),
            (re.compile(r'^山东少儿'), '山东少儿.png'),
            (re.compile(r'^山东生活'), '山东生活.png'),
            (re.compile(r'^山东体育'), '山东体育.png'),
            (re.compile(r'^山东文旅'), '山东文旅.png'),
            (re.compile(r'^山东新闻'), '山东新闻.png'),
            (re.compile(r'^山东综艺'), '山东综艺.png'),
            (re.compile(r'^居家购物'), '居家购物.png'),
            (re.compile(r'^山东居家购物'), '居家购物.png'),
            (re.compile(r'^海洋频道'), '海洋频道.png'),
            (re.compile(r'^山东海洋'), '海洋频道.png'),
            (re.compile(r'^山东(.+)'), lambda m: f'山东{m.group(1)}.png'),
        ])

        return rules

    # ════════════════════════════════════════════════════════
    #  智能模糊匹配
    # ════════════════════════════════════════════════════════

    def _strip_suffix(self, text: str, suffixes: Tuple[str, ...]) -> str:
        """从文本末尾移除匹配的后缀（仅移除一个最长的匹配项）。"""
        for suffix in suffixes:
            if text.endswith(suffix) and len(text) > len(suffix):
                return text[:-len(suffix)].strip()
        return text

    def _get_variants(self, name: str) -> List[str]:
        """生成频道名的多个归一化变体（从保守到激进）。

        返回的变体列表顺序：
        1. 仅去除括号/特殊字符
        2. 去除画质后缀（高清/HD/4K 等）
        3. 去除通用后缀（频道/电视台 等）
        4+ . 上述各版本的紧凑形式（去除 -_. 空格等分隔符）
        """
        # 基础清理：去除括号、特殊标记
        cleaned = self._SPECIAL_CHARS_RE.sub('', name)
        cleaned = re.sub(r'\s+', '', cleaned).strip()
        if not cleaned:
            return []

        variants: List[str] = [cleaned]

        # 去除画质后缀
        v1 = self._strip_suffix(cleaned, self._QUALITY_SUFFIXES)
        if v1 != cleaned and v1:
            variants.append(v1)
        else:
            v1 = cleaned

        # 去除通用后缀
        v2 = self._strip_suffix(v1, self._GENERIC_SUFFIXES)
        if v2 != v1 and v2:
            variants.append(v2)

        # 为每个变体创建紧凑版本（去除分隔符）
        compact_variants: List[str] = []
        for v in variants:
            compact = self._SEPARATOR_RE.sub('', v)
            if compact and compact != v:
                compact_variants.append(compact)
        variants.extend(compact_variants)

        return variants

    def _match_variant(self, variant: str) -> Optional[Tuple[str, float]]:
        """对单个归一化变体进行匹配，返回 (logo_stem, score) 或 None。"""
        if not variant or len(variant) < 2:
            return None

        vl = variant.lower()

        # ── 精确匹配（大小写不敏感）──
        if vl in self._logo_map:
            return (self._logo_map[vl], 1.0)

        # 紧凑版本精确匹配
        compact = self._SEPARATOR_RE.sub('', vl)
        if compact in self._logo_compact_map:
            return (self._logo_compact_map[compact], 1.0)

        # ── 前缀/包含匹配 ──
        best_match: Optional[str] = None
        best_score: float = 0.0

        for logo_stem in self._logo_stems_sorted:  # 按长度降序
            ll = logo_stem.lower()

            # 频道名以 logo 名开头（如 "济南新闻综合" 以 "济南新闻" 开头）
            if vl.startswith(ll):
                score = len(ll) / len(vl)
                if score > best_score:
                    best_score = score
                    best_match = logo_stem
                if score >= 0.99:
                    break  # 几乎精确
                continue

            # logo 名以频道名开头（如频道 "CCTV1" 匹配 logo "CCTV1+"）
            if ll.startswith(vl) and len(vl) >= 3:
                score = len(vl) / len(ll) * 0.9
                if score > best_score:
                    best_score = score
                    best_match = logo_stem
                continue

            # 包含匹配（logo 名是频道名的子串，或反之）
            if len(ll) >= 3:
                if ll in vl:
                    score = len(ll) / len(vl) * 0.8
                    if score > best_score:
                        best_score = score
                        best_match = logo_stem
                    continue
                if vl in ll:
                    score = len(vl) / len(ll) * 0.75
                    if score > best_score:
                        best_score = score
                        best_match = logo_stem
                    continue

        if best_match and best_score >= 0.5:
            return (best_match, best_score)

        return None

    def _fuzzy_match(self, name: str) -> Optional[str]:
        """使用序列相似度进行模糊匹配（最后兜底）。"""
        if not name or len(name) < 2:
            return None

        nl = name.lower()
        best_ratio: float = 0.0
        best_match: Optional[str] = None

        for logo_stem in self._logo_stems_sorted:
            ll = logo_stem.lower()
            # 快速预过滤：长度差异过大则跳过
            max_len = max(len(nl), len(ll))
            min_len = min(len(nl), len(ll))
            if min_len < max_len * 0.4:
                continue
            ratio = SequenceMatcher(None, nl, ll).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = logo_stem
                if ratio >= 0.95:
                    break

        if best_match and best_ratio >= 0.6:
            return best_match

        return None

    # ════════════════════════════════════════════════════════
    #  对外接口
    # ════════════════════════════════════════════════════════

    def match_stem_exact(self, name: str) -> Optional[str]:
        """只做规则与精确匹配，返回台标文件名（不含扩展名）；不做相似度兜底。

        本地台标目录按文件名查找时使用：宁可没有台标，也不要把相近频道的
        台标套到当前频道上。
        """
        if not name:
            return None

        for pattern, logo_file in self.rules:
            m = pattern.match(name)
            if m:
                value = logo_file(m) if callable(logo_file) else logo_file
                return os.path.splitext(value)[0] if value else None

        for variant in self._get_variants(name):
            result = self._match_variant(variant)
            if result:
                stem, score = result
                if score >= 1.0:
                    return stem

        # 频道名常见「CCTV-1 综合」「CCTV-5 体育」：去掉分隔符与末尾描述词后精确比对
        compact = self._SEPARATOR_RE.sub('', name).lower()
        for suffix in ('综合', '新闻', '体育', '财经', '电影', '综艺', '纪录',
                       '少儿', '音乐', '戏曲', '国际', '中文', '高清', '超高清'):
            if compact.endswith(suffix) and len(compact) > len(suffix):
                stem_key = compact[:-len(suffix)]
                if stem_key in self._logo_compact_map:
                    return self._logo_compact_map[stem_key]
        return None

    def match(self, name: str) -> Optional[str]:
        if not name:
            return None

        # ── 第一层：正则规则匹配（处理 CCTV 编号等特殊情况）──
        for pattern, logo_file in self.rules:
            m = pattern.match(name)
            if m:
                if callable(logo_file):
                    result = logo_file(m)
                    if result:
                        return self.base_url + result
                    return None
                if logo_file:
                    return self.base_url + logo_file
                return None

        # ── 第二层：智能模糊匹配 ──
        variants = self._get_variants(name)
        best_logo: Optional[str] = None
        best_score: float = 0.0

        for variant in variants:
            result = self._match_variant(variant)
            if result:
                logo_stem, score = result
                if score > best_score:
                    best_score = score
                    best_logo = logo_stem
                if score >= 1.0:
                    break  # 精确匹配，无需继续

        if best_logo:
            return self.base_url + best_logo + '.png'

        # ── 第三层：序列相似度模糊匹配 ──
        # 使用最保守的变体（第一个）进行模糊匹配
        fuzzy_input = variants[0] if variants else name
        fuzzy_result = self._fuzzy_match(fuzzy_input)
        if fuzzy_result:
            return self.base_url + fuzzy_result + '.png'

        return None

    def match_all(self, channels: list, overwrite: bool = False) -> list:
        results = []
        for i, ch in enumerate(channels):
            name = ch.get('name', '')
            current_logo = ch.get('logo', '')
            if not overwrite and current_logo:
                continue
            logo = self.match(name)
            if logo:
                results.append({
                    'index': i,
                    'name': name,
                    'logo': logo,
                    'old_logo': current_logo,
                })
        return results
