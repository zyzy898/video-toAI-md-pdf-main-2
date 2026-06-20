import {
  UploadIcon,
  ShieldIcon,
  CheckListIcon,
  SubtitleIcon,
  FileIcon,
  GlobeIcon,
  LinkIcon,
  ClockIcon,
  EditIcon
} from '../components/icons/Icons.jsx';

/**
 * 9 个核心能力卡片的数据。
 * tags 中以 accent 标记的会着色为强调色。
 */
export const capabilities = [
  {
    tag: '输入',
    Icon: UploadIcon,
    title: '多通道上传',
    desc: '本地文件、批量、分片续传与远程链接四路并行；大文件 8MB 一片，断网刷新都能从断点继续传。',
    tags: [
      { label: '断点续传', accent: true },
      { label: '批量' },
      { label: 'URL 直达' }
    ]
  },
  {
    tag: '安全',
    Icon: ShieldIcon,
    title: '四层内容风控',
    desc: '指纹黑名单 → 视觉抽帧 → 备用视觉模型 → 关键词词库，逐层校验。上传前与分析前各跑一次，命中即隔离。',
    tags: [
      { label: '四层校验', accent: true },
      { label: '结果缓存' },
      { label: '自动隔离' }
    ]
  },
  {
    tag: '分析',
    Icon: CheckListIcon,
    title: '结构化步骤输出',
    desc: '标准步骤识别失败会自动退到候选步骤，再退到时间线摘要；置信度低的步骤会再让模型"看图说话"补强。',
    tags: [
      { label: '三级降级', accent: true },
      { label: '看图增强' },
      { label: '质量打分' }
    ]
  },
  {
    tag: '字幕',
    Icon: SubtitleIcon,
    title: '字幕工作台',
    desc: 'faster-whisper（CTranslate2）常驻转写，按模型与参数缓存结果；一键导出 SRT / VTT / TXT，可关键词检索字幕，点哪行视频跳哪行。',
    tags: [
      { label: 'SRT · VTT · TXT', accent: true },
      { label: '关键词检索' },
      { label: '点选跳转' }
    ]
  },
  {
    tag: '导出',
    Icon: FileIcon,
    title: 'Markdown · PDF 双导出',
    desc: 'AI 输出经过安全清洗再渲染；PDF 自动适配 Windows / Linux 中文字体；结果包内含截图、字幕、原视频与步骤数据。',
    tags: [
      { label: 'Markdown', accent: true },
      { label: 'PDF', accent: true },
      { label: '步骤 JSON' }
    ]
  },
  {
    tag: '模型',
    Icon: GlobeIcon,
    title: '多模型平台路由',
    desc: '同一套调用代码自动适配 Ark / OpenAI / DeepSeek / Qwen 等平台；不支持的能力会自动降级到字幕分析路线。',
    tags: [
      { label: 'Ark', accent: true },
      { label: 'OpenAI' },
      { label: 'DeepSeek' },
      { label: 'Qwen' }
    ]
  },
  {
    tag: '链接',
    Icon: LinkIcon,
    title: '智能 URL 导入',
    desc: 'B 站、抖音、小红书有专属解析；通用页面靠浏览器抓取 + 模型识别 + yt-dlp 兜底，多层回退保下载成功率。',
    tags: [
      { label: 'B站 / 抖音 / 小红书', accent: true },
      { label: '反爬兜底' },
      { label: 'Cookie 复用' }
    ]
  },
  {
    tag: '历史',
    Icon: ClockIcon,
    title: '历史与自动清理',
    desc: '无登录系统也能多人共存：每个浏览器独立隔离历史。后台定时回收：上传 24 小时清，输出与历史 72 小时清。',
    tags: [
      { label: '无登录隔离', accent: true },
      { label: '定时清理' },
      { label: '磁盘可控' }
    ]
  },
  {
    tag: '编辑',
    Icon: EditIcon,
    title: '步骤可编辑重生成',
    desc: '结果支持拖拽排序、改写、增删步骤。保存后会按你编辑后的版本重新生成 Markdown 与 PDF，文档永远跟编辑一致。',
    tags: [
      { label: '拖拽排序', accent: true },
      { label: '一键重生成' },
      { label: '所改即所得' }
    ]
  }
];
