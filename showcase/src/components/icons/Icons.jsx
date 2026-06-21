/**
 * 集中存放所有 inline SVG 图标，便于复用。
 * 每个组件支持透传 className / size 属性。
 */

const baseProps = (className) => ({
  viewBox: '0 0 24 24',
  className: className || 'ico',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round'
});

export const PlayIcon = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className || 'ico'} fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
);

export const UploadIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

export const ShieldIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

export const CheckListIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <polyline points="9 11 12 14 22 4" />
    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
  </svg>
);

export const SubtitleIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <polygon points="23 7 16 12 23 17 23 7" />
    <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
  </svg>
);

export const FileIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
  </svg>
);

export const GlobeIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z" />
  </svg>
);

export const LinkIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </svg>
);

export const ClockIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

export const EditIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
  </svg>
);

export const SettingsIcon = ({ className }) => (
  <svg {...baseProps(className || 'ico-sm')}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.05a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.05a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

export const InboxIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M22 11v3a2 2 0 0 1-2 2h-7l-3 3-3-3H2v-3" />
    <path d="M22 6V3a2 2 0 0 0-2-2H2v9h20" />
    <line x1="12" y1="11" x2="12" y2="17" />
    <line x1="9" y1="14" x2="15" y2="14" />
  </svg>
);

export const CheckIcon = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className || 'ico-sm'} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

export const DownloadIcon = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className || 'ico-sm'} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

export const ArrowRightIcon = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className || 'ico-sm'} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12" />
    <polyline points="13 6 19 12 13 18" />
  </svg>
);

export const ChevronRightIcon = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className || ''} width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

export const BoltIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </svg>
);

export const MobileIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <path d="M6 22h12" />
    <path d="M12 18v4" />
  </svg>
);

export const LockIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <rect x="3" y="11" width="18" height="11" rx="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);

export const InfoIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

export const ServerIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <line x1="22" y1="12" x2="18" y2="12" />
    <line x1="6" y1="12" x2="2" y2="12" />
    <line x1="12" y1="6" x2="12" y2="2" />
    <line x1="12" y1="22" x2="12" y2="18" />
    <circle cx="12" cy="12" r="6" />
  </svg>
);

export const ActivityIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
  </svg>
);

export const WrenchIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
);

export const PaletteIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <circle cx="13.5" cy="6.5" r=".5" />
    <circle cx="17.5" cy="10.5" r=".5" />
    <circle cx="8.5" cy="7.5" r=".5" />
    <circle cx="6.5" cy="12.5" r=".5" />
    <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01-.23-.26-.38-.61-.38-1 0-.83.67-1.5 1.5-1.5H16c3.31 0 6-2.69 6-6 0-4.97-4.48-9-10-9z" />
  </svg>
);

export const GithubIcon = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className || 'ico'} fill="currentColor" aria-hidden="true">
    <path d="M12 1.5a10.5 10.5 0 0 0-3.32 20.47c.53.1.72-.23.72-.51 0-.25-.01-.92-.01-1.8-2.7.5-3.4-.66-3.62-1.27-.12-.32-.66-1.27-1.13-1.53-.39-.21-.94-.72-.01-.73.87-.01 1.49.8 1.7 1.13.99 1.67 2.57 1.2 3.2.92.1-.72.39-1.2.7-1.48-2.45-.28-5.02-1.23-5.02-5.45 0-1.2.43-2.19 1.13-2.96-.11-.28-.49-1.41.11-2.93 0 0 .92-.29 3.02 1.13a10.2 10.2 0 0 1 5.5 0c2.1-1.43 3.02-1.13 3.02-1.13.6 1.52.22 2.65.11 2.93.7.77 1.13 1.75 1.13 2.96 0 4.23-2.58 5.16-5.04 5.44.4.34.75 1.01.75 2.04 0 1.48-.01 2.67-.01 3.03 0 .29.19.63.73.51A10.5 10.5 0 0 0 12 1.5z" />
  </svg>
);

export const SunIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <circle cx="12" cy="12" r="4.2" />
    <line x1="12" y1="2.5" x2="12" y2="5" />
    <line x1="12" y1="19" x2="12" y2="21.5" />
    <line x1="2.5" y1="12" x2="5" y2="12" />
    <line x1="19" y1="12" x2="21.5" y2="12" />
    <line x1="5.1" y1="5.1" x2="6.9" y2="6.9" />
    <line x1="17.1" y1="17.1" x2="18.9" y2="18.9" />
    <line x1="5.1" y1="18.9" x2="6.9" y2="17.1" />
    <line x1="17.1" y1="6.9" x2="18.9" y2="5.1" />
  </svg>
);

export const MoonIcon = ({ className }) => (
  <svg {...baseProps(className)}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
);


