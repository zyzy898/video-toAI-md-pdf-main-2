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
    desc: '本地文件、批量、分片续传与远程链接四路接入；磁盘分片可跨后端重启保留，浏览器刷新后需重新选择同一文件，再续传服务端缺少的分片。',
    tags: [
      { label: '断点续传', accent: true },
      { label: '同文件重选' },
      { label: '<500MB' }
    ]
  },
  {
    tag: '安全',
    Icon: ShieldIcon,
    title: '分阶段内容风控',
    desc: '上传阶段只做指纹 / 黑名单与缓存预检，阻断时删除暂存文件；任务进入 analyzing 后先执行主视觉检测，不可用时才尝试备用视觉模型或字幕关键词，分析阶段命中可隔离。',
    tags: [
      { label: '上传预检', accent: true },
      { label: '分析前视觉检测' },
      { label: '结果缓存' }
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
    title: '高精度字幕工作台',
    desc: 'faster-whisper（CTranslate2）常驻转写，三层精度增强叠加：ffmpeg 降噪归一化 + 热词偏置 + LLM 同音字纠错；一键导出 SRT / VTT / TXT，可关键词检索、点哪行视频跳哪行。',
    tags: [
      { label: '同音字纠错', accent: true },
      { label: '降噪归一化' },
      { label: 'SRT · VTT · TXT' },
      { label: '点选跳转' }
    ]
  },
  {
    tag: '导出',
    Icon: FileIcon,
    title: 'Markdown · PDF 双导出',
    desc: 'AI 输出经过安全清洗再渲染；结果 ZIP 包含 Markdown、生成成功时的 PDF、steps.json、步骤截图与 SRT / VTT / TXT 字幕，不包含原视频。',
    tags: [
      { label: 'Markdown', accent: true },
      { label: 'PDF', accent: true },
      { label: '步骤 JSON' }
    ]
  },
  {
    tag: '模型',
    Icon: GlobeIcon,
    title: '三类模型路由',
    desc: '路由实现分为 Ark、OpenAI、OpenAI 兼容三类；DeepSeek、Qwen 可作为兼容端点示例。不支持视频能力时转入字幕分析路线。',
    tags: [
      { label: 'Ark', accent: true },
      { label: 'OpenAI' },
      { label: 'OpenAI 兼容' }
    ]
  },
  {
    tag: '链接',
    Icon: LinkIcon,
    title: '智能 URL 导入',
    desc: 'B 站、抖音、小红书有专属解析；通用页面依次尝试浏览器抓取、模型识别与 yt-dlp，多条可选路径提升站点适配鲁棒性。',
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
    desc: '无登录系统也能按浏览器隔离历史。后台定时回收上传、输出与历史文件，用于降低长期磁盘增长；部署时仍需监控容量。',
    tags: [
      { label: '无登录隔离', accent: true },
      { label: '定时清理' },
      { label: '降低磁盘增长' }
    ]
  },
  {
    tag: '编辑',
    Icon: EditIcon,
    title: '步骤可编辑重生成',
    desc: '结果支持拖拽排序、改写、增删步骤。保存后会按编辑版本重新生成 Markdown，并在 PDF 生成成功时更新 PDF。',
    tags: [
      { label: '拖拽排序', accent: true },
      { label: '一键重生成' },
      { label: '所改即所得' }
    ]
  }
];
