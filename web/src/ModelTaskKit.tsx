import { useState } from 'react';
import { Check, Copy, Download } from 'lucide-react';
import { gameNames } from './games';
import type { GameId } from './types';
import './model-task-kit.css';

const prompt = '请解压附件，按 START_HERE.md 准备环境，阅读 MODEL_TASK.md，使用包内工具实际编译、练习并改进你的 Bot。最终交付完整的单文件 bot.cpp，另附中文开发总结，说明实际运行了哪些检查、结果如何，以及哪些环节未能完成。';
const archives: Record<GameId, string> = {
  bomberman: 'llm-arena-devkit.zip',
  gomoku: 'llm-arena-gomoku-devkit.zip',
};

export function ModelTaskKit({game}: {game: GameId}) {
  const [copyState, setCopyState] = useState<'ready' | 'copied' | 'manual'>('ready');
  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopyState('copied');
    } catch {
      setCopyState('manual');
    }
  }
  return <section className="model-task-kit" aria-labelledby="model-task-title">
    <div>
      <h2 id="model-task-title">给模型发任务</h2>
      <p>把 ZIP 和提示词一起发给编程代理，收到 bot.cpp 后在下方导入。</p>
    </div>
    <div className="kit-actions">
      <a className="button" href={`/devkits/${archives[game]}`} download><Download aria-hidden="true" />下载{gameNames[game]}任务包</a>
      <button type="button" onClick={copyPrompt}>
        {copyState === 'copied' ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        <span aria-live="polite">{copyState === 'copied' ? '已复制提示词' : '复制提示词'}</span>
      </button>
    </div>
    {copyState === 'manual' && <label className="kit-manual" role="status">请手动复制提示词
      <textarea readOnly rows={3} value={prompt} onFocus={e => e.currentTarget.select()} />
    </label>}
  </section>;
}
