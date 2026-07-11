import {
  BoltIcon,
  MobileIcon,
  UploadIcon,
  SubtitleIcon,
  GlobeIcon,
  ShieldIcon,
  LockIcon,
  InfoIcon,
  ServerIcon,
  ActivityIcon,
  WrenchIcon,
  PaletteIcon
} from '../components/icons/Icons.jsx';

/**
 * 工程化优化与落地实践 · 13 张卡。
 * 列表条目使用 dangerouslySetInnerHTML 渲染，因为原文里有 <b> / <code> 标签。
 */
export const engineeringCards = [
  {
    Icon: BoltIcon,
    title: '前端渲染性能',
    items: [
      '历史抽屉走<b>虚拟列表</b>：只渲染可见行与少量缓冲，降低长历史列表的 DOM 数量和滚动开销',
      '结果区与超长 Markdown 区<b>滚动到才渲染</b>，减少离屏内容的渲染工作',
      '关键容器声明独立的渲染边界，让浏览器更容易隔离局部更新，减少跨区域重排',
      '位移 / 透明度动画优先走 GPU 合成，降低主线程布局与绘制压力'
    ],
    tags: [
      { label: '虚拟列表', accent: true },
      { label: '按需渲染' },
      { label: 'GPU 合成' }
    ]
  },
  {
    Icon: MobileIcon,
    title: '移动 / 弱设备自适应',
    items: [
      '启动时检测<b>粗粒度移动输入（≤900px 且 pointer: coarse）、系统"减少动效"偏好与省流量模式</b>，命中任一即切到性能模式',
      '性能模式下 Hero 动画、流光按钮、平滑滚动等装饰性效果<b>自动降级为静态</b>，降低弱设备的渲染负载',
      '分析进度的轮询频率自适应：桌面 5 秒 / 移动 9 秒，节流网络与电量',
      '动画实现遵循系统的"减少动效"偏好，优先降低不必要的动态效果'
    ],
    tags: [
      { label: '设备识别', accent: true },
      { label: '无障碍' },
      { label: '省电策略' }
    ]
  },
  {
    Icon: UploadIcon,
    title: '分片上传与断点续传',
    items: [
      '分片上传默认按 <b>8MB 一片</b>；单文件须 <b>&lt;500MB</b>，达到或超过 500MB 会拒绝并提示先裁剪',
      '分片与会话写入后端磁盘，服务重启后仍可查询已接收分片并继续缺口',
      '浏览器刷新或重开后不会保留 File 字节；需<b>重新选择同一文件</b>，再按服务端清单补传缺失分片',
      '网络重试会跳过服务端已确认的分片；当前分片在响应丢失时仍可能重传'
    ],
    tags: [
      { label: '断点续传', accent: true },
      { label: '8MB 分片' },
      { label: '后端重启可续' }
    ]
  },
  {
    Icon: SubtitleIcon,
    title: '长视频自动预处理',
    items: [
      '按视频时长 + 体积分四档：<b>标准 / 长视频 / 超长 / 必须先裁剪</b>',
      '长视频自动压缩、必要时切片重拼，处理副本只用一次，原始视频不动',
      '超长档自动关掉视频理解、关掉联网搜索、强制只生成摘要版，降低超时与显存压力',
      '超过 90 分钟或体积达到 500MB 会直接拒绝，并明确提示用户先裁剪'
    ],
    tags: [
      { label: '自动切片', accent: true },
      { label: '参数自动收紧' },
      { label: '早拒绝早友好', kind: 'warn' }
    ]
  },
  {
    Icon: SubtitleIcon,
    title: '字幕精度三层增强 + 自学习',
    items: [
      '<b>方案 B · 转写前</b>：ffmpeg 高通滤波 + FFT 降噪 + EBU R128 响度归一化，把背景音乐 / 低频嗡声 / 忽大忽小的人声先清干净再喂给 ASR',
      '<b>方案 A · 解码时</b>：领域热词 + 上下文种子提示在解码阶段就把识别偏向正确术语，从源头压制近音错字',
      '<b>转写后 · LLM 纠错</b>：把字幕分批送模型，仅修正同音 / 近音错别字（如「铁子」→「帖子」），并以<b>长度比例护栏</b>降低误改原意的风险',
      '<b>自学习反馈环</b>：每处纠错用 jieba 切词提炼「错→对」词对，写入可复查日志并沉淀成热词表；后续视频转写可自动回灌，无需重启'
    ],
    tags: [
      { label: '降噪归一化', accent: true },
      { label: '同音字纠错', accent: true },
      { label: '热词迭代', kind: 'success' }
    ]
  },
  {
    Icon: GlobeIcon,
    title: '三类模型路由统一接入',
    items: [
      '路由层分为 <b>Ark、OpenAI、OpenAI 兼容</b>三类，并声明聊天、文件、视频与联网搜索等能力',
      '系统根据后端 .env 配置选择路由；DeepSeek、Qwen 可作为 OpenAI 兼容端点示例，不是独立 provider 实现',
      '切到不支持视频理解的路由时，系统会改走字幕抽取路线并记录实际链路',
      '调用路由不支持的能力时返回可读错误，便于调整后端模型配置或关闭对应能力'
    ],
    tags: [
      { label: '能力声明', accent: true },
      { label: '自动选路' },
      { label: '可读错误' }
    ]
  },
  {
    Icon: ShieldIcon,
    title: '分阶段内容风控 + 结果缓存',
    items: [
      '上传预检只做<b>文件指纹 / 黑名单匹配与已有缓存判定</b>，不在上传阶段运行全部视觉检测',
      '任务进入 analyzing 后、内容分析前先执行主视觉检测；主检测不可用时，才尝试备用视觉模型或字幕关键词检查',
      '上传阶段命中阻断会删除暂存文件；分析阶段命中阻断的文件可进入隔离目录',
      '同一视频与模型配置的判定结果会缓存，用于减少重复视觉检测与 API 调用'
    ],
    tags: [
      { label: '指纹黑名单', accent: true },
      { label: '视觉风控', accent: true },
      { label: '省 API 费' }
    ]
  },
  {
    Icon: LockIcon,
    title: '渲染安全 & 后端状态持久化',
    items: [
      'AI 输出先经过<b>清洗管线</b>再渲染，降低 XSS 与脚本注入风险',
      '不需要登录系统，靠每个浏览器一份匿名 ID 做<b>多用户历史隔离</b>，自己只看到自己的记录',
      'API Key 与模型选择由后端 <b>.env</b> 统一配置，前端不保存模型或密钥偏好',
      '异步任务状态持久化在后端；刷新后可按 task_id 恢复 queued / analyzing / completed / failed / cancelled 五个分析状态，uploading 单独表示上传会话'
    ],
    tags: [
      { label: '输出清洗', accent: true },
      { label: '后端 .env' },
      { label: '任务恢复' }
    ]
  },
  {
    Icon: InfoIcon,
    title: '错误处理 & 引导式 UX',
    items: [
      '统一错误层把后端的状态码、风控原因、分段策略等信息<b>拼成一句完整可读的错误说明</b>，避免"请求失败"这种黑盒提示',
      '模型配置缺失时返回明确提示，指向后端 <b>.env</b>；前端不提供模型 / API Key 设置抽屉',
      '风险与策略提示分级展示：阻断卡片放到最显眼、长视频建议放在结果上方、自动降级在结果上注明原因',
      '持久任务可查询、取消或重试，刷新后继续展示服务端记录的状态'
    ],
    tags: [
      { label: '配置错误提示', accent: true },
      { label: '分级提示' },
      { label: '错误归因' }
    ]
  },
  {
    Icon: ServerIcon,
    title: '后端并发与资源治理',
    items: [
      '截图生成、批量分析、faster-whisper 推理的<b>并发线程数都可配置</b>，按机器配置随时调整',
      'faster-whisper 模型可常驻内存，减少重复加载；字幕缓存键包含模型大小 / 精度 / beam / VAD，降低调参后误复用风险',
      '生产环境可用 Waitress 提供多线程 WSGI 请求处理；Python GIL 与 CPU 密集型工作仍会限制吞吐',
      '后台清理线程定期回收：<b>上传文件 24 小时清，输出与历史 72 小时清</b>，用于降低磁盘增长；部署仍需容量监控'
    ],
    tags: [
      { label: '参数化并发', accent: true },
      { label: '模型常驻' },
      { label: '自动清理', kind: 'success' }
    ]
  },
  {
    Icon: ActivityIcon,
    title: '进度可观测 & 质量评分',
    items: [
      '任务以 queued / analyzing / completed / failed / cancelled 状态持久化，支持查询、取消、重试与刷新恢复',
      '每份结果都打一个 0–1 的<b>质量分</b>，综合考量步骤完整度、时间顺序、置信度、来源可靠性、数量是否合理',
      '模型识别效果不足时会尝试标准步骤 → 候选步骤 → 时间线摘要等降级路径；全部失败时返回明确失败状态与原因',
      '每个分析任务都有 <b>task_id</b>，可用于定位该任务的状态与错误'
    ],
    tags: [
      { label: '阶段化进度', accent: true },
      { label: '质量分' },
      { label: '请求追踪' }
    ]
  },
  {
    Icon: WrenchIcon,
    title: '工程基础设施',
    items: [
      '提交代码前可运行<b>行尾空格、文件末尾换行、合并冲突标记、中文乱码与 Python 语法</b>等检查，尽早发现常见问题',
      '前端 ESLint 配置覆盖 TypeScript 与 React Hooks 等规则，用于在合并前发现常见问题',
      '前端开发环境通过本地代理转发后端接口，减少本地跨域配置',
      '常量、类型、工具函数与组件按职责分层，并统一路径别名以降低维护成本'
    ],
    tags: [
      { label: '提交前体检', accent: true },
      { label: '类型检查' },
      { label: '分层清晰' }
    ]
  },
  {
    Icon: PaletteIcon,
    title: '设计系统 & 视觉一致性',
    items: [
      '颜色、圆角、阴影、间距等视觉规范统一定义在<b>设计变量</b>里，需要换肤或微调时只改一处',
      '组件层用 utility 写样式（小巧灵活），主题层走变量（统一可换），两者并存不冲突',
      '主要交互动效共用缓动曲线和时长区间，减少动效节奏不一致',
      '滚动条预留固定宽度，避免内容出现 / 消失时整页轻微抖动'
    ],
    tags: [
      { label: '设计变量', accent: true },
      { label: '样式分层' },
      { label: '动效节奏统一' }
    ]
  }
];
