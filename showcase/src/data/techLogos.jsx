import {
  SiReact,
  SiTypescript,
  SiVite,
  SiTailwindcss,
  SiFlask,
  SiPython,
  SiFfmpeg,
  SiOpenai,
  SiMarkdown,
  SiDocker,
  SiNginx,
  SiGit
} from 'react-icons/si';

/**
 * 技术栈品牌 logo 列表，喂给 <LogoLoop />。
 * 每项的 node 是 react-icons 里的纯 SVG，颜色继承父容器（我们在 CSS 里统一染色）。
 */
export const techLogos = [
  { node: <SiReact />, title: 'React', href: 'https://react.dev' },
  { node: <SiTypescript />, title: 'TypeScript', href: 'https://www.typescriptlang.org' },
  { node: <SiVite />, title: 'Vite', href: 'https://vitejs.dev' },
  { node: <SiTailwindcss />, title: 'Tailwind CSS', href: 'https://tailwindcss.com' },
  { node: <SiFlask />, title: 'Flask', href: 'https://flask.palletsprojects.com' },
  { node: <SiPython />, title: 'Python', href: 'https://www.python.org' },
  { node: <SiFfmpeg />, title: 'FFmpeg', href: 'https://ffmpeg.org' },
  { node: <SiOpenai />, title: 'Whisper · OpenAI', href: 'https://openai.com/research/whisper' },
  { node: <SiMarkdown />, title: 'Markdown', href: 'https://daringfireball.net/projects/markdown' },
  { node: <SiDocker />, title: 'Docker', href: 'https://www.docker.com' },
  { node: <SiNginx />, title: 'Nginx', href: 'https://nginx.org' },
  { node: <SiGit />, title: 'Git', href: 'https://git-scm.com' }
];
