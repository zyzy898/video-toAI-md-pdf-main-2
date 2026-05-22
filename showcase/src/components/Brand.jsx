/**
 * 顶栏 / 页脚通用品牌区域。size 控制 brand-logo 尺寸（默认正常，small 用于工作台模拟内）。
 * 当 as != 'a' 时不输出 href，避免在 div 上挂 href 这种无效属性。
 */
export default function Brand({ size = 'normal', as = 'a', href = '#hero' }) {
  const Tag = as;
  const logoStyle =
    size === 'small'
      ? { width: '1.6rem', height: '1.6rem', borderRadius: '0.45rem' }
      : undefined;
  const iconSize = size === 'small' ? 11 : 14;

  const props = { className: 'brand' };
  if (Tag === 'a') props.href = href;

  return (
    <Tag {...props}>
      <span className="brand-logo" aria-hidden="true" style={logoStyle}>
        <svg viewBox="0 0 24 24" width={iconSize} height={iconSize} fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      </span>
      <span>VIDEO INSIGHTS</span>
    </Tag>
  );
}
