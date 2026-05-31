/**
 * InterviewAgent 前端主逻辑 v5
 *
 * 修复：
 * 1. TTS 朗读：flush() 始终关闭指示器；speakText 正确传 voice
 * 2. 面试结束：bool 强制转换防止 "True" 字符串问题（服务端已修复）
 * 3. 记忆系统：get_memory 主动拉取；clear_long_memory 清除历史
 * 4. RAG 检索结果弹窗
 * 5. 结束面试按钮 + 确认弹窗
 * 6. 防止面试中重复点击开始
 * 7. 再次面试等待旧 WS 关闭
 * 8. 气泡间距修复 + 追问标签独立渲染修复
 */

'use strict';

const WS_BASE  = `ws://${location.host}`;
const API_BASE = `${location.protocol}//${location.host}`;

const DIFFICULTY_LABEL = {
  easy:   { text: '简单', cls: 'badge-green' },
  medium: { text: '中等', cls: 'badge-blue'  },
  hard:   { text: '困难', cls: 'badge-red'   },
};

const SKILL_META = {
  quiz: {
    title: '📝 快速测验',
    placeholder: '输入主题（可选），如：RAG、Python、系统设计',
    examples: `<strong>使用示例：</strong><br>
• <code>（空）</code> → 随机出一道题<br>
• <code>RAG</code> → 出一道 RAG 相关题<br>
• <code>Python</code> → 出一道 Python 基础题<br><br>
<strong>提交答案：</strong>出题后再次执行，输入框填写答案即可评分`,
  },
  teach: {
    title: '📖 知识讲解',
    placeholder: '输入要讲解的概念，如：注意力机制、BM25、LangGraph',
    examples: `<strong>使用示例：</strong><br>
• <code>注意力机制</code> → 讲解 Attention 原理<br>
• <code>BM25</code> → 讲解 BM25 算法<br>
• <code>LangGraph</code> → 讲解框架原理<br>
• <code>RAG 和 Fine-tuning 的区别</code> → 对比讲解`,
  },
  project: {
    title: '💡 项目亮点提炼',
    placeholder: '描述你的项目经历，AI 帮你提炼面试亮点',
    examples: `<strong>使用示例：</strong><br>
粘贴项目描述，输出 STAR 格式亮点 + 可能追问问题<br><br>
例：<code>我负责开发了一个 RAG 知识库，使用 Weaviate + BM25 双路召回...</code>`,
  },
  compare: {
    title: '⚖️ 技术对比',
    placeholder: '输入两个技术，如：BM25 vs 向量检索',
    examples: `<strong>使用示例：</strong><br>
• <code>BM25 vs 向量检索</code><br>
• <code>RAG vs Fine-tuning</code><br>
• <code>Redis vs MySQL</code><br>
• <code>LangChain vs LlamaIndex</code><br>
输出结构化对比表格`,
  },
};

/* ══ ASCII / Markdown 表格解析器 ════════════════════════════════════ */
const TableParser = {
  parse(text) {
    if (!text) return text;
    const lines  = text.split('\n');
    const result = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (line.trim().startsWith('|') && line.includes('|', 1)) {
        const tbl = [];
        while (i < lines.length && lines[i].trim().startsWith('|')) {
          tbl.push(lines[i]); i++;
        }
        result.push(this._pipeTable(tbl));
        continue;
      }
      if (/^[\s\-═─━=_]{8,}$/.test(line.trim())) {
        const tbl = this._collectAscii(lines, i);
        if (tbl.rows.length >= 1) {
          result.push(this._asciiTable(tbl));
          i += tbl.consumed;
          continue;
        }
      }
      result.push(line);
      i++;
    }
    return result.join('\n');
  },
  _collectAscii(lines, sepIdx) {
    let consumed = 1;
    const headerLines = [];
    if (sepIdx > 0 && lines[sepIdx - 1].trim())
      headerLines.push(lines[sepIdx - 1]);
    const rows = [];
    let j = sepIdx + 1;
    while (j < lines.length && lines[j].trim() &&
           !/^[\s\-═─━=_]{6,}$/.test(lines[j].trim())) {
      rows.push(lines[j]); j++; consumed++;
    }
    return { headerLines, rows, consumed };
  },
  _splitRow(row) {
    return row.trim().split(/\s{2,}/).map(c => c.trim()).filter(Boolean);
  },
  _asciiTable({ headerLines, rows }) {
    const headers = headerLines.flatMap(l => this._splitRow(l));
    const dataRows = rows.map(l => this._splitRow(l)).filter(r => r.length);
    if (!headers.length && !dataRows.length) return '';
    const head = headers.length
      ? `<thead><tr>${headers.map(h => `<th>${this._e(h)}</th>`).join('')}</tr></thead>`
      : '';
    const body = dataRows.map(r =>
      `<tr>${r.map(c => `<td>${this._e(c)}</td>`).join('')}</tr>`
    ).join('');
    return `<table>${head}<tbody>${body}</tbody></table>`;
  },
  _pipeTable(lines) {
    const rows = lines
      .filter(l => !/^\s*\|[\s\-:|]+\|\s*$/.test(l))
      .map(l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim()));
    if (!rows.length) return '';
    const [hdr, ...body] = rows;
    return `<table>
      <thead><tr>${hdr.map(h => `<th>${this._e(h)}</th>`).join('')}</tr></thead>
      <tbody>${body.map(r =>
        `<tr>${r.map(c => `<td>${this._e(c)}</td>`).join('')}</tr>`
      ).join('')}</tbody>
    </table>`;
  },
  _e(t) {
    return String(t||'')
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  },
};

/* ══ Markdown 渲染器 ════════════════════════════════════════════════ */
const MD = {
  render(text) {
    if (!text) return '';
    text = TableParser.parse(text);
    const tables = [];
    text = text.replace(/<table[\s\S]*?<\/table>/gi, m => {
      tables.push(m); return `\x00T${tables.length - 1}\x00`;
    });
    let html = text
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    html = html.replace(/```[\s\S]*?```/g, m => {
      const code = m.slice(3,-3).replace(/^[a-zA-Z]*\n/,'');
      return `<pre><code>${code}</code></pre>`;
    });
    html = html.replace(/`([^`\n]+)`/g,'<code>$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
    html = html.replace(/__(.+?)__/g,'<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g,'<em>$1</em>');
    html = html.replace(/\n/g,'<br>');
    html = html.replace(/\x00T(\d+)\x00/g, (_,i) => tables[+i]);
    return html;
  },
};

/* ══ TTS 播放器 ══════════════════════════════════════════════════════ */
class TtsPlayer {
  constructor() {
    this._chunks  = [];
    this._enabled = true;
  }
  setEnabled(v)  { this._enabled = v; }
  get enabled()  { return this._enabled; }

  pushChunk(buf) {
    if (!this._enabled) return;
    this._chunks.push(buf instanceof ArrayBuffer ? buf : buf.buffer);
  }

  async flush() {
    if (!this._enabled || !this._chunks.length) {
      this._chunks = [];
      App._setTtsIndicator(false);
      return;
    }
    const blob   = new Blob(this._chunks, { type: 'audio/mpeg' });
    this._chunks = [];
    const url    = URL.createObjectURL(blob);
    const audio  = new Audio(url);
    App._setTtsIndicator(true);
    const done = () => {
      URL.revokeObjectURL(url);
      App._setTtsIndicator(false);
    };
    audio.onended = done;
    audio.onerror = done;
    try { await audio.play(); } catch(e) { done(); }
  }

  clear() { this._chunks = []; }
}

/* ══ 录音器 ══════════════════════════════════════════════════════════ */
class AudioRecorder {
  constructor(onReady) {
    this._onReady  = onReady;
    this._recorder = null;
    this._chunks   = [];
    this._stream   = null;
  }
  async start() {
    try {
      this._stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this._chunks = [];
      const mime   = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/ogg';
      this._recorder = new MediaRecorder(this._stream, { mimeType: mime });
      this._recorder.ondataavailable = e => { if (e.data.size > 0) this._chunks.push(e.data); };
      this._recorder.onstop = () => {
        const blob = new Blob(this._chunks, { type: mime });
        blob.arrayBuffer().then(buf => this._onReady(buf));
      };
      this._recorder.start(100);
      return true;
    } catch(e) {
      App.showToast('无法获取麦克风权限，请检查浏览器设置', 'error');
      return false;
    }
  }
  stop() {
    if (this._recorder?.state !== 'inactive') this._recorder?.stop();
    this._stream?.getTracks().forEach(t => t.stop());
    this._stream = null;
  }
}

/* ══ WebSocket 客户端 ════════════════════════════════════════════════ */
class WsClient {
  constructor(id, handlers) {
    this._id       = id;
    this._handlers = handlers;
    this._ws       = null;
    this._closed   = false;
  }
  connect() {
    this._ws = new WebSocket(`${WS_BASE}/ws/${this._id}`);
    this._ws.onopen    = ()  => this._handlers.onOpen?.();
    this._ws.onclose   = ev  => { if (!this._closed) this._handlers.onClose?.(ev); };
    this._ws.onerror   = e   => console.error('[WS]', e);
    this._ws.onmessage = ev  => {
      if (ev.data instanceof Blob)
        ev.data.arrayBuffer().then(buf => this._handlers.onBinary?.(buf));
      else {
        try { this._handlers.onMessage?.(JSON.parse(ev.data)); }
        catch(e) { console.warn('[WS] parse error', ev.data); }
      }
    };
  }
  send(data)   { if (this._ws?.readyState === 1) this._ws.send(JSON.stringify(data)); }
  sendBin(buf) { if (this._ws?.readyState === 1) this._ws.send(buf); }
  closeAsync() {
    return new Promise(resolve => {
      if (!this._ws || this._ws.readyState === WebSocket.CLOSED) {
        resolve(); return;
      }
      this._closed = true;
      this._ws.onclose = () => resolve();
      this._ws.close();
      setTimeout(resolve, 2000);
    });
  }
  get ready() { return this._ws?.readyState === 1; }
}

/* ══ 主控制器 ════════════════════════════════════════════════════════ */
const App = {
  sessionId:       null,
  ws:              null,
  recorder:        null,
  ttsPlayer:       new TtsPlayer(),
  isRecording:     false,
  interviewActive: false,
  cameraStream:    null,
  currentSkill:    null,
  _memTab:         'short',
  _lastSkillText:  '',

  memData: {
    short: {
      qa_history:           [],
      current_question_idx: 0,
      current_difficulty:   'medium',
      total_questions:      0,
    },
    long: {
      weaknesses: [],
    },
  },

  lastReport: null,

  /* ── 初始化 ─────────────────────────────────────────────────────── */
  init() {
    this.recorder = new AudioRecorder(buf => {
      if (this.ws?.ready) this.ws.sendBin(buf);
    });
    document.getElementById('resume-file')
      .addEventListener('change', e => this._uploadResume(e.target.files[0]));
    document.getElementById('voice-select')
      .addEventListener('change', e => {
        this.ttsPlayer.setEnabled(e.target.value !== '');
      });
    this._updateConnStatus('disconnected');
  },

  /* ── 开始面试 ────────────────────────────────────────────────────── */
  async startInterview() {
    if (this.interviewActive) {
      this.showToast('面试进行中，请先结束当前面试或等待完成', 'warning');
      return;
    }

    const jdText = document.getElementById('jd-input').value.trim();
    if (!jdText) { this.showToast('请填写岗位 JD', 'error'); return; }

    const resumeText     = document.getElementById('resume-input').value.trim();
    const totalQuestions = parseInt(document.getElementById('total-questions').value);
    const voice          = document.getElementById('voice-select').value;

    this.ttsPlayer.setEnabled(voice !== '');
    this.sessionId  = this._uuid();
    this.lastReport = null;

    this.memData.short = {
      qa_history: [], current_question_idx: 0,
      current_difficulty: 'medium', total_questions: totalQuestions,
    };

    this._hideFinishBar();
    this._setStartBtn(true);

    this._connectWs({
      type: 'start', jd_text: jdText, resume_text: resumeText,
      total_questions: totalQuestions,
      voice: voice || null, user_id: 'web_user',
    });
    this._showThinking('正在分析 JD，生成题目...');
  },

  /* ── 再次面试 ────────────────────────────────────────────────────── */
  async restartInterview() {
    this.closeReportModal();
    this.interviewActive = false;

    if (this.ws) {
      await this.ws.closeAsync();
      this.ws = null;
    }

    document.getElementById('chat-box').innerHTML          = '';
    document.getElementById('progress-wrap').style.display  = 'none';
    document.getElementById('input-area').style.display     = 'none';
    document.getElementById('skill-panel').style.display    = 'none';
    document.getElementById('memory-btn').style.display     = 'none';
    document.getElementById('finish-early-btn').style.display = 'none';
    document.getElementById('rag-btn').style.display        = 'none';
    document.getElementById('welcome-screen').style.display = 'flex';
    this._hideFinishBar();
    this._hideThinking();
    this._setStartBtn(false);
    this._updateConnStatus('disconnected');

    this.memData.short = {
      qa_history: [], current_question_idx: 0,
      current_difficulty: 'medium', total_questions: 0,
    };
    this.lastReport = null;
  },

  /* ── 建立 WS ─────────────────────────────────────────────────────── */
  _connectWs(startPayload) {
    this.ws = new WsClient(this.sessionId, {
      onOpen:    () => {
        this._updateConnStatus('connected');
        this.ws.send(startPayload);
      },
      onMessage: d  => this._onMsg(d),
      onBinary:  b  => this.ttsPlayer.pushChunk(b),
      onClose:   () => {
        this._updateConnStatus('disconnected');
        if (this.interviewActive)
          this.showToast('连接断开，请刷新重试', 'warning');
      },
    });
    this.ws.connect();
    this._updateConnStatus('connecting');
  },

  /* ── 消息处理 ────────────────────────────────────────────────────── */
  _onMsg(data) {
    const { type } = data;

    if (data.memory_snapshot) {
      const snap = data.memory_snapshot;
      if (Array.isArray(snap.qa_history))
        this.memData.short.qa_history = snap.qa_history;
      if (snap.current_question_idx != null)
        this.memData.short.current_question_idx = snap.current_question_idx;
      if (snap.current_difficulty)
        this.memData.short.current_difficulty = snap.current_difficulty;
      if (snap.total_questions)
        this.memData.short.total_questions = snap.total_questions;
      if (Array.isArray(snap.long_term_weaknesses) && snap.long_term_weaknesses.length)
        this.memData.long.weaknesses = snap.long_term_weaknesses;
    }

    if (type === 'memory_data') {
      const st = data.short_term || {};
      const lt = data.long_term  || {};
      if (Array.isArray(st.qa_history))
        this.memData.short.qa_history = st.qa_history;
      if (st.current_question_idx != null)
        this.memData.short.current_question_idx = st.current_question_idx;
      if (st.current_difficulty)
        this.memData.short.current_difficulty = st.current_difficulty;
      if (st.total_questions)
        this.memData.short.total_questions = st.total_questions;
      if (Array.isArray(lt.weaknesses))
        this.memData.long.weaknesses = lt.weaknesses;
      if (document.getElementById('memory-modal').style.display !== 'none')
        this._renderMemory();
      return;
    }

    if (type === 'rag_data') {
      this._renderRagData(data);
      return;
    }

    if (type === 'toast') {
      this.showToast(data.msg || '', data.level || 'info');
      return;
    }

    if (type === 'question') {
      this._hideThinking();
      this._showInterviewUI();
      this._updateProgress(data.index, data.total, data.difficulty);
      // 普通问题，isFollowup = false
      this._appendBubble('ai', data.text, 'question', false);
    }
    else if (type === 'followup') {
      this._hideThinking();
      // ★ 追问消息，isFollowup = true
      this._appendBubble('ai', data.text, 'followup', true);
    }
    else if (type === 'finished') {
      this._hideThinking();
      this.interviewActive = false;

      const farewell = data.farewell || '';
      if (farewell) this._appendBubble('ai', farewell, 'finished', false);

      this.lastReport = {
        final_report:           data.report              || {},
        study_plan:             data.study_plan          || {},
        github_recommendations: data.github_recommendations || [],
      };

      if (data.memory_snapshot?.long_term_weaknesses?.length)
        this.memData.long.weaknesses = data.memory_snapshot.long_term_weaknesses;

      this._showFinishBar();
      document.getElementById('finish-early-btn').style.display = 'none';
    }
    else if (type === 'skill_reply') {
      this._hideThinking();
      this._lastSkillText = data.text || '';
      this._appendBubble('ai', data.text, 'skill-reply', false);
      const wr = document.getElementById('modal-result-wrap');
      const el = document.getElementById('modal-result');
      if (wr && el) {
        el.innerHTML     = MD.render(data.text);
        wr.style.display = 'block';
      }
      this._setSkillBtnState(false);
    }
    else if (type === 'stt_result') {
      this._hideThinking();
      if (data.text) {
        document.getElementById('answer-input').value = data.text;
        this.showToast('🎤 识别完成，请确认后按 Enter 发送', 'success');
      } else {
        this.showToast(data.message || '未识别到语音，请重试', 'warning');
      }
    }
    else if (type === 'tts_start') {
      this.ttsPlayer.clear();
    }
    else if (type === 'tts_end') {
      this.ttsPlayer.flush();
    }
    else if (type === 'error') {
      this._hideThinking();
      this.showToast(data.message || '发生错误', 'error');
      this._appendBubble('ai', `❌ ${data.message}`, 'system', false);
      this._setStartBtn(false);
      this._setSkillBtnState(false);
    }
    else if (type === 'pong') { /* 心跳响应，忽略 */ }
  },

  /* ── 提交回答 ────────────────────────────────────────────────────── */
  submitAnswer() {
    const input = document.getElementById('answer-input');
    const text  = input.value.trim();
    if (!text) { this.showToast('回答不能为空', 'warning'); return; }
    if (!this.ws?.ready) { this.showToast('连接已断开，请刷新', 'error'); return; }

    this._appendBubble('user', text, '', false);
    input.value = '';
    this.ws.send({ type: 'answer', text });
    this._showThinking('AI 正在评估...');
  },

  handleKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.submitAnswer(); }
  },

  /* ── 语音录制 ────────────────────────────────────────────────────── */
  async startRecording(e) {
    if (e) e.preventDefault();
    if (this.isRecording) return;
    const ok = await this.recorder.start();
    if (!ok) return;
    this.isRecording = true;
    document.getElementById('mic-btn').classList.add('recording');
    this.showToast('🎤 录音中，松开后识别（结果填入输入框）', 'info');
  },

  stopRecording() {
    if (!this.isRecording) return;
    this.isRecording = false;
    document.getElementById('mic-btn').classList.remove('recording');
    this.recorder.stop();
    this._showThinking('语音识别中...');
  },

  /* ── TTS 手动朗读 ────────────────────────────────────────────────── */
  speakText(text) {
    if (!text || !text.trim()) {
      this.showToast('没有可朗读的内容', 'warning');
      return;
    }
    const voice = document.getElementById('voice-select').value;
    if (!voice) {
      this.showToast('请先在左侧配置中选择 TTS 音色', 'warning');
      return;
    }
    if (!this.ws?.ready) {
      this.showToast('WebSocket 未连接，无法朗读', 'warning');
      return;
    }
    this.ws.send({ type: 'tts_speak', text: text.slice(0, 600), voice });
    this._setTtsIndicator(true);
  },

  speakSkillResult() {
    this.speakText(this._lastSkillText);
  },

  /* ── 摄像头 ──────────────────────────────────────────────────────── */
  async toggleCamera() {
    const wrap  = document.getElementById('camera-wrap');
    const video = document.getElementById('camera-video');
    const btn   = document.getElementById('camera-btn');
    if (this.cameraStream) {
      this.cameraStream.getTracks().forEach(t => t.stop());
      this.cameraStream  = null;
      video.srcObject    = null;
      wrap.style.display = 'none';
      btn.textContent    = '📷 开启摄像头';
    } else {
      try {
        this.cameraStream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject   = this.cameraStream;
        wrap.style.display = 'block';
        btn.textContent    = '📷 关闭摄像头';
      } catch(e) { this.showToast('无法获取摄像头权限', 'error'); }
    }
  },

  /* ── 技能弹窗 ─────────────────────────────────────────────────────── */
  openSkill(name) {
    this.currentSkill   = name;
    this._lastSkillText = '';
    const meta = SKILL_META[name] || {};
    document.getElementById('modal-title').textContent  = meta.title || name;
    document.getElementById('modal-input').placeholder  = meta.placeholder || '';
    document.getElementById('modal-input').value        = '';
    document.getElementById('skill-examples').innerHTML = meta.examples || '';
    document.getElementById('modal-result-wrap').style.display = 'none';
    document.getElementById('modal-result').innerHTML   = '';
    this._setSkillBtnState(false);
    document.getElementById('skill-modal').style.display = 'flex';
    setTimeout(() => document.getElementById('modal-input').focus(), 80);
  },

  runSkill() {
    if (!this.currentSkill) return;
    if (!this.ws?.ready) { this.showToast('请先开始面试', 'warning'); return; }
    const input = document.getElementById('modal-input').value.trim();
    this._setSkillBtnState(true);
    const wr = document.getElementById('modal-result-wrap');
    const el = document.getElementById('modal-result');
    wr.style.display = 'block';
    el.innerHTML     = '<span style="color:var(--dim)">处理中，请稍候...</span>';
    this.ws.send({ type: 'skill', skill_name: this.currentSkill, user_input: input });
    this._showThinking(`技能 [${this.currentSkill}] 处理中...`);
  },

  _setSkillBtnState(loading) {
    const btn = document.getElementById('modal-run-btn');
    if (!btn) return;
    btn.disabled    = loading;
    btn.textContent = loading ? '处理中...' : '执行';
  },

  closeSkillModal(e) {
    if (e && e.target !== document.getElementById('skill-modal')) return;
    document.getElementById('skill-modal').style.display = 'none';
    this.currentSkill = null;
  },

  /* ── 报告弹窗 ─────────────────────────────────────────────────────── */
  openReportModal() {
    if (!this.lastReport) { this.showToast('暂无报告数据', 'warning'); return; }
    const { final_report, study_plan, github_recommendations } = this.lastReport;
    ReportRenderer.render(final_report, study_plan, github_recommendations);
  },

  closeReportModal(e) {
    if (e && e.target !== document.getElementById('report-modal')) return;
    document.getElementById('report-modal').style.display = 'none';
  },

  /* ── 结束面试（确认弹窗）────────────────────────────────────────── */
  confirmForceFinish() {
    document.getElementById('confirm-modal').style.display = 'flex';
  },

  closeConfirmModal(e) {
    if (e && e.target !== document.getElementById('confirm-modal')) return;
    document.getElementById('confirm-modal').style.display = 'none';
  },

  doForceFinish() {
    document.getElementById('confirm-modal').style.display = 'none';
    if (!this.ws?.ready) { this.showToast('连接已断开', 'error'); return; }
    this.ws.send({ type: 'force_finish' });
    this._showThinking('正在生成评估报告...');
    document.getElementById('finish-early-btn').style.display = 'none';
    this.interviewActive = false;
  },

  /* ── 记忆面板 ─────────────────────────────────────────────────────── */
  openMemoryPanel() {
    document.querySelectorAll('.mem-tab').forEach((t,i) =>
      t.classList.toggle('active', i === 0));
    this._memTab = 'short';
    document.getElementById('memory-modal').style.display = 'flex';
    if (this.ws?.ready) {
      this.ws.send({ type: 'get_memory', user_id: 'web_user' });
    }
    this._renderMemory();
  },

  refreshMemory() {
    if (this.ws?.ready) {
      this.ws.send({ type: 'get_memory', user_id: 'web_user' });
      this.showToast('正在刷新记忆数据...', 'info');
    } else {
      this._renderMemory();
      this.showToast('WebSocket 未连接，显示本地缓存', 'warning');
    }
  },

  closeMemoryPanel(e) {
    if (e && e.target !== document.getElementById('memory-modal')) return;
    document.getElementById('memory-modal').style.display = 'none';
  },

  switchMemTab(tab, btn) {
    this._memTab = tab;
    document.querySelectorAll('.mem-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    this._renderMemory();
  },

  confirmClearMemory() {
    if (!confirm('确定要清除所有历史长期记忆（薄弱点记录）吗？此操作不可撤销。')) return;
    if (!this.ws?.ready) {
      this.showToast('WebSocket 未连接，请先开始面试', 'warning');
      return;
    }
    this.ws.send({ type: 'clear_long_memory', user_id: 'web_user' });
    this.memData.long.weaknesses = [];
    this._renderMemory();
  },

  _renderMemory() {
    const el = document.getElementById('memory-content');
    el.innerHTML = '';
    if (this._memTab === 'short') {
      this._renderShortMem(el);
    } else {
      this._renderLongMem(el);
    }
  },

  _renderShortMem(el) {
    const s       = this.memData.short;
    const history = s.qa_history || [];
    const diffLabel = DIFFICULTY_LABEL[s.current_difficulty]?.text
                      || s.current_difficulty || 'medium';

    const progSec = document.createElement('div');
    progSec.className = 'mem-section';
    progSec.innerHTML = `
      <h4>📊 当前进度</h4>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
        <span class="mem-tag">
          已答：${history.length} / ${s.total_questions || '?'} 题
        </span>
        <span class="mem-tag">当前难度：${diffLabel}</span>
      </div>
    `;
    el.appendChild(progSec);

    const qaSec = document.createElement('div');
    qaSec.className = 'mem-section';
    qaSec.innerHTML = `<h4>📝 本次对话记录（${history.length} 条）</h4>`;

    if (!history.length) {
      qaSec.insertAdjacentHTML('beforeend',
        '<div class="dim" style="margin-top:6px">暂无记录（回答题目后实时更新）</div>');
    } else {
      history.forEach((qa, i) => {
        const q     = qa.question || '';
        const a     = qa.answer   || '';
        const score = qa.score    || {};
        const items = [];
        if (score.correctness != null) items.push(`正确性:${score.correctness}`);
        if (score.depth       != null) items.push(`深度:${score.depth}`);
        if (score.structure   != null) items.push(`表达:${score.structure}`);
        const div = document.createElement('div');
        div.className = 'mem-qa';
        div.innerHTML = `
          <div>
            <span class="role role-q">Q${i+1}.</span>
            ${this._esc(q.slice(0,100))}${q.length>100?'…':''}
          </div>
          <div style="margin-top:4px">
            <span class="role role-a">A.</span>
            <span class="dim">
              ${this._esc(a.slice(0,120))}${a.length>120?'…':''}
            </span>
          </div>
          ${items.length
            ? `<div class="score-line">📊 ${items.join(' · ')}</div>`
            : ''}
        `;
        qaSec.appendChild(div);
      });
    }
    el.appendChild(qaSec);
  },

  _renderLongMem(el) {
    const weaknesses = this.memData.long.weaknesses || [];
    const sec = document.createElement('div');
    sec.className = 'mem-section';
    sec.innerHTML = `<h4>⚠️ 历史累积薄弱点（${weaknesses.length} 条）</h4>`;

    if (!weaknesses.length) {
      sec.insertAdjacentHTML('beforeend',
        '<div class="dim" style="margin-top:6px">暂无历史薄弱点（面试结束后写入）</div>');
    } else {
      const wrap = document.createElement('div');
      wrap.className   = 'tag-list';
      wrap.style.marginTop = '8px';
      weaknesses.forEach(w => {
        wrap.insertAdjacentHTML('beforeend',
          `<span class="mem-tag">${this._esc(w)}</span>`);
      });
      sec.appendChild(wrap);
    }
    el.appendChild(sec);

    const curWeak = this.lastReport?.final_report?.weaknesses || [];
    if (curWeak.length) {
      const sec2 = document.createElement('div');
      sec2.className   = 'mem-section';
      sec2.style.marginTop = '14px';
      sec2.innerHTML   = `<h4>🔴 本次面试薄弱点（${curWeak.length} 条）</h4>`;
      const wrap2 = document.createElement('div');
      wrap2.className  = 'tag-list';
      wrap2.style.marginTop = '8px';
      curWeak.forEach(w => {
        wrap2.insertAdjacentHTML('beforeend',
          `<span class="mem-tag danger">${this._esc(w)}</span>`);
      });
      sec2.appendChild(wrap2);
      el.appendChild(sec2);
    }
  },

  /* ── RAG 检索结果面板 ────────────────────────────────────────────── */
  openRagPanel() {
    const el = document.getElementById('rag-content');
    el.innerHTML = '<div class="dim" style="text-align:center;padding:24px">加载中...</div>';
    document.getElementById('rag-modal').style.display = 'flex';
    if (this.ws?.ready) {
      this.ws.send({ type: 'get_rag' });
    } else {
      el.innerHTML = '<div class="dim" style="text-align:center;padding:24px">请先开始面试</div>';
    }
  },

  refreshRag() {
    if (this.ws?.ready) {
      document.getElementById('rag-content').innerHTML =
        '<div class="dim" style="text-align:center;padding:24px">刷新中...</div>';
      this.ws.send({ type: 'get_rag' });
    }
  },

  closeRagModal(e) {
    if (e && e.target !== document.getElementById('rag-modal')) return;
    document.getElementById('rag-modal').style.display = 'none';
  },

  _renderRagData(data) {
    const el      = document.getElementById('rag-content');
    if (!el) return;
    const sources = data.rag_sources || [];
    const context = data.rag_context || '';
    const total   = data.total       || 0;

    if (!sources.length && !context) {
      el.innerHTML = `
        <div class="dim" style="text-align:center;padding:24px">
          暂无 RAG 检索结果（面试启动后才有数据）
        </div>`;
      document.getElementById('rag-modal').style.display = 'flex';
      return;
    }

    let html = `
      <div style="margin-bottom:14px;display:flex;align-items:center;gap:8px">
        <span class="badge badge-blue">共检索到 ${total} 条</span>
        <span class="dim" style="font-size:13px">展示前 ${sources.length} 条</span>
      </div>
    `;

    if (sources.length) {
      html += '<div class="report-section"><h4>📄 检索来源</h4>';
      sources.forEach((src, i) => {
        const text  = (src.text || src.content || '').slice(0, 300);
        const score = src.score != null
          ? (typeof src.score === 'number' ? src.score.toFixed(3) : src.score)
          : '-';
        const fname = src.metadata?.file_name || src.source || `来源 ${i+1}`;
        html += `
          <div style="background:var(--bg3);border:1px solid var(--border);
                      border-radius:6px;padding:10px 13px;margin-bottom:8px;
                      font-size:13px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
              <span style="color:var(--primary-h);font-weight:600">#${i+1}</span>
              <span class="dim">${this._esc(String(fname))}</span>
              <span class="badge badge-grey" style="margin-left:auto">
                相关度: ${score}
              </span>
            </div>
            <div style="color:var(--text);line-height:1.6">
              ${this._esc(text)}${text.length >= 300 ? '...' : ''}
            </div>
          </div>
        `;
      });
      html += '</div>';
    }

    if (context) {
      html += `
        <div class="report-section">
          <h4>📝 注入 LLM 的上下文（前 3000 字符）</h4>
          <div style="background:var(--bg3);border:1px solid var(--border);
                      border-radius:6px;padding:12px;font-size:13px;
                      line-height:1.7;white-space:pre-wrap;
                      max-height:320px;overflow-y:auto;">
            ${this._esc(context)}
          </div>
        </div>
      `;
    }

    el.innerHTML = html;
    document.getElementById('rag-modal').style.display = 'flex';
  },

  /* ── 结束操作栏 ──────────────────────────────────────────────────── */
  _showFinishBar() {
    document.getElementById('finish-bar')?.remove();
    const bar     = document.createElement('div');
    bar.id        = 'finish-bar';
    bar.className = 'finish-actions';
    bar.innerHTML = `
      <button class="btn btn-primary" onclick="App.openReportModal()">
        📊 查看完整报告
      </button>
      <button class="btn btn-outline" onclick="App.openMemoryPanel()">
        🧠 查看记忆
      </button>
      <button class="btn btn-outline" onclick="App.openRagPanel()">
        🔍 查看 RAG
      </button>
      <button class="btn btn-ghost" onclick="App.restartInterview()">
        🔄 再来一次
      </button>
    `;
    document.querySelector('.interview-area').appendChild(bar);
    document.getElementById('input-area').style.display = 'none';
  },

  _hideFinishBar() {
    document.getElementById('finish-bar')?.remove();
  },

  /* ── 文件上传 ────────────────────────────────────────────────────── */
  async _uploadResume(file) {
    if (!file) return;
    document.getElementById('upload-filename').textContent = file.name;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const resp = await fetch(`${API_BASE}/upload/resume`, { method:'POST', body:fd });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        this.showToast(`上传失败: ${err.detail || resp.statusText}`, 'error');
        return;
      }
      const data = await resp.json();
      document.getElementById('resume-input').value = data.text;
      this.showToast(`简历解析成功（${data.char_count} 字符）`, 'success');
    } catch(e) { this.showToast(`上传异常: ${e.message}`, 'error'); }
  },

  /* ── UI 辅助 ─────────────────────────────────────────────────────── */
  _showInterviewUI() {
    if (this.interviewActive) return;
    document.getElementById('welcome-screen').style.display   = 'none';
    document.getElementById('progress-wrap').style.display    = 'block';
    document.getElementById('input-area').style.display       = 'block';
    document.getElementById('skill-panel').style.display      = 'block';
    document.getElementById('memory-btn').style.display       = 'inline-flex';
    document.getElementById('finish-early-btn').style.display = 'inline-flex';
    document.getElementById('rag-btn').style.display          = 'inline-flex';
    this._setStartBtn(false);
    this.interviewActive = true;
    const badge = document.getElementById('session-badge');
    badge.textContent   = `会话: ${this.sessionId.slice(0, 8)}`;
    badge.style.display = 'inline-block';
  },

  _updateProgress(index, total, difficulty) {
    document.getElementById('progress-text').textContent = `第 ${index} / ${total} 题`;
    const pct = total > 0 ? (index / total) * 100 : 0;
    document.getElementById('progress-fill').style.width = `${pct}%`;
    const info  = DIFFICULTY_LABEL[difficulty] || { text: difficulty, cls:'badge-grey' };
    const badge = document.getElementById('difficulty-badge');
    badge.textContent = info.text;
    badge.className   = `badge ${info.cls}`;
  },

  /**
   * ★ 核心修改：追问标签独立渲染，不放在气泡内部
   *
   * 结构变为：
   *   .msg-content
   *     ├── .followup-tag-wrap  （仅追问时存在，气泡外部上方）
   *     │     └── .followup-tag
   *     └── .msg-bubble
   *           └── 气泡内容（不含追问标签）
   *
   * @param {'ai'|'user'} role
   * @param {string}      text        原始文本
   * @param {string}      extraClass  bubble 额外 class
   * @param {boolean}     isFollowup  是否显示追问标签
   */
  _appendBubble(role, text, extraClass = '', isFollowup = false) {
    const box  = document.getElementById('chat-box');
    const isAI = role === 'ai';

    const wrap = document.createElement('div');
    wrap.className = `msg ${isAI ? 'msg-ai' : 'msg-user'}`;

    // ★ 追问标签：独立放在气泡容器外（.msg-content 内、.msg-bubble 上方）
    const followupHtml = isFollowup
      ? `<div class="followup-tag-wrap">
           <span class="followup-tag">🔍 追问</span>
         </div>`
      : '';

    // AI 消息用 MD 渲染，用户消息转义
    const bubbleHtml = isAI ? MD.render(text) : this._esc(text);

    // AI 气泡悬停时显示朗读按钮
    const actionsHtml = isAI ? `
      <div class="msg-actions">
        <button class="msg-action-btn"
                data-text="${this._attrEsc(text)}"
                onclick="App.speakText(this.dataset.text)">
          🔊 朗读
        </button>
      </div>
    ` : '';

    wrap.innerHTML = `
      <div class="msg-avatar">${isAI ? '🤖' : '👤'}</div>
      <div class="msg-content">
        ${followupHtml}
        <div class="msg-bubble ${extraClass}">${bubbleHtml}</div>
        ${actionsHtml}
      </div>
    `;

    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
  },

  _showThinking(text = 'AI 正在思考...') {
    document.getElementById('thinking-text').textContent = text;
    document.getElementById('thinking-bar').style.display = 'flex';
  },
  _hideThinking() {
    document.getElementById('thinking-bar').style.display = 'none';
  },
  _setTtsIndicator(show) {
    const el = document.getElementById('tts-indicator');
    if (el) el.style.display = show ? 'inline-block' : 'none';
  },
  _setStartBtn(loading) {
    const btn = document.getElementById('start-btn');
    btn.disabled    = loading;
    btn.textContent = loading ? '⏳ 生成中...' : '🚀 开始面试';
  },
  _updateConnStatus(s) {
    const map = {
      connected:    { text: '已连接 ●', cls: 'badge-green' },
      connecting:   { text: '连接中…',  cls: 'badge-amber' },
      disconnected: { text: '未连接',   cls: 'badge-grey'  },
    };
    const el   = document.getElementById('conn-status');
    const info = map[s] || map.disconnected;
    el.textContent = info.text;
    el.className   = `badge ${info.cls}`;
  },

  showToast(msg, type = 'info') {
    const c = document.getElementById('toast-container');
    const t = document.createElement('div');
    t.className   = `toast ${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => {
      t.style.opacity    = '0';
      t.style.transition = 'opacity .3s';
      setTimeout(() => t.remove(), 300);
    }, 3200);
  },

  _esc(text) {
    return String(text || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/\n/g, '<br>');
  },

  _attrEsc(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  },

  _uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  },
};

/* ══ 报告渲染器 ════════════════════════════════════════════════════ */
const ReportRenderer = {
  render(report, studyPlan, githubRecs) {
    const el = document.getElementById('report-content');
    el.innerHTML = '';
    el.appendChild(this._overview(report));
    el.appendChild(this._dimensions(report));
    el.appendChild(this._topics(report));
    el.appendChild(this._tags(report));
    if (studyPlan && Object.keys(studyPlan).length)
      el.appendChild(this._studyPlan(studyPlan));
    if (githubRecs?.length)
      el.appendChild(this._github(githubRecs));
    document.getElementById('report-modal').style.display = 'flex';
  },

  _overview(r) {
    const score = r.overall_score ?? 0;
    const recMap = {
      strong_hire: { text: '强烈推荐 ✅', cls: 'badge-green' },
      hire:        { text: '推荐录用 ✅', cls: 'badge-green' },
      weak_hire:   { text: '勉强推荐 ⚠️', cls: 'badge-amber' },
      no_hire:     { text: '不推荐 ❌',   cls: 'badge-red'   },
    };
    const rec  = recMap[r.recommendation]
               || { text: r.recommendation || '-', cls: 'badge-grey' };
    const cx = 44, cy = 44, radius = 38;
    const circ = 2 * Math.PI * radius;
    const dash  = (score / 100) * circ;
    const div  = document.createElement('div');
    div.className = 'score-overview';
    div.innerHTML = `
      <div class="score-circle-wrap">
        <svg width="88" height="88" viewBox="0 0 88 88">
          <circle cx="${cx}" cy="${cy}" r="${radius}"
                  fill="none" stroke="var(--bg3)" stroke-width="8"/>
          <circle cx="${cx}" cy="${cy}" r="${radius}"
                  fill="none" stroke="var(--primary)" stroke-width="8"
                  stroke-dasharray="${dash} ${circ}" stroke-linecap="round"/>
        </svg>
        <div class="score-circle-num">${score}</div>
      </div>
      <div class="score-meta">
        <h3>${r.jd_title || '面试评估报告'}</h3>
        <p style="margin-bottom:6px">${r.summary || ''}</p>
        <span class="badge ${rec.cls}">${rec.text}</span>
        ${r.interviewer_comment
          ? `<p style="margin-top:8px;font-size:13px;color:var(--dim)">
               💬 ${r.interviewer_comment}
             </p>`
          : ''}
      </div>
    `;
    return div;
  },

  _dimensions(r) {
    const dims = r.dimension_scores || {};
    const nameMap = {
      technical_knowledge:  '技术知识',
      problem_solving:      '问题解决',
      system_design:        '系统设计',
      communication:        '表达沟通',
      practical_experience: '实战经验',
      learning_ability:     '学习潜力',
    };
    const sec = document.createElement('div');
    sec.className = 'report-section';
    sec.innerHTML = '<h4>🎯 六维能力评分</h4><div class="dim-grid"></div>';
    const grid = sec.querySelector('.dim-grid');
    for (const [key, label] of Object.entries(nameMap)) {
      const s   = typeof dims[key] === 'number' ? dims[key] : 0;
      const pct = Math.min(s * 10, 100);
      const col = s>=8?'var(--success)':s>=6?'var(--primary)':
                  s>=4?'var(--warning)':'var(--danger)';
      grid.insertAdjacentHTML('beforeend', `
        <div class="dim-item">
          <div class="dim-name">${label}</div>
          <div class="dim-bar">
            <div class="dim-fill" style="width:${pct}%;background:${col}"></div>
          </div>
          <div class="dim-score" style="color:${col}">${s} / 10</div>
        </div>
      `);
    }
    return sec;
  },

  _topics(r) {
    const topics = r.topic_performance || [];
    if (!topics.length) return document.createElement('div');
    const sec = document.createElement('div');
    sec.className = 'report-section';
    sec.innerHTML = '<h4>📌 主题表现</h4><div class="topic-list"></div>';
    const list = sec.querySelector('.topic-list');
    const pm = {
      good:    { text: '良好 ✅', cls: 'badge-green' },
      average: { text: '一般 ➖', cls: 'badge-blue'  },
      weak:    { text: '薄弱 ❌', cls: 'badge-red'   },
    };
    topics.forEach(tp => {
      const p = pm[tp.performance] || { text: tp.performance, cls: 'badge-grey' };
      list.insertAdjacentHTML('beforeend', `
        <div class="topic-item">
          <span class="topic-name">${tp.topic || '-'}</span>
          <span class="badge ${p.cls}">${p.text}</span>
          <span class="dim" style="font-size:13px">${tp.comment || ''}</span>
        </div>
      `);
    });
    return sec;
  },

  _tags(r) {
    const defs = [
      { key:'strengths',  label:'✅ 优势',   bg:'rgba(34,197,94,.15)', col:'var(--success)'   },
      { key:'weaknesses', label:'⚠️ 薄弱点', bg:'rgba(239,68,68,.15)',col:'var(--danger)'    },
      { key:'highlights', label:'⭐ 亮点',   bg:'rgba(245,158,11,.15)',col:'var(--warning)'   },
      { key:'concerns',   label:'🔍 关注点', bg:'rgba(99,102,241,.15)',col:'var(--primary-h)' },
    ];
    const sec = document.createElement('div');
    sec.className = 'report-section';
    defs.forEach(({ key, label, bg, col }) => {
      let items = r[key] || [];
      if (!Array.isArray(items)) items = [String(items)];
      items = items.filter(Boolean);
      if (!items.length) return;
      const wrap = document.createElement('div');
      wrap.style.marginBottom = '10px';
      wrap.innerHTML = `
        <div class="dim" style="font-size:13px;margin-bottom:5px">${label}</div>
        <div class="tag-list">
          ${items.map(i =>
            `<span class="tag" style="background:${bg};color:${col}">${i}</span>`
          ).join('')}
        </div>
      `;
      sec.appendChild(wrap);
    });
    return sec;
  },

  _studyPlan(plan) {
    const sec = document.createElement('div');
    sec.className = 'report-section';
    sec.innerHTML = '<h4>📚 个性化复习计划</h4>';
    if (plan.overall_advice) {
      sec.insertAdjacentHTML('beforeend',
        `<p class="dim" style="font-size:14px;margin-bottom:10px">
           💡 ${plan.overall_advice}
         </p>`);
    }
    (plan.weeks || []).forEach(w => {
      const goals     = Array.isArray(w.goals)
        ? w.goals.join('；') : (w.goals || '');
      const resources = Array.isArray(w.resources)
        ? w.resources.join('，') : (w.resources || '');
      sec.insertAdjacentHTML('beforeend', `
        <div class="week-card">
          <h5>📅 第 ${w.week||'-'} 周：${w.theme||'-'}
            （每天 ${w.daily_hours||'-'} 小时）</h5>
          ${goals     ? `<p>🎯 ${goals}</p>`     : ''}
          ${resources ? `<p>📖 ${resources}</p>` : ''}
        </div>
      `);
    });
    return sec;
  },

  _github(recs) {
    const sec = document.createElement('div');
    sec.className = 'report-section';
    sec.innerHTML = '<h4>🔗 GitHub 学习资源</h4>';
    recs.forEach(item => {
      const repos = item.repos || [];
      sec.insertAdjacentHTML('beforeend', `
        <div style="margin-bottom:12px">
          <div class="dim" style="font-size:13px;margin-bottom:6px">
            📚 ${item.weakness || '-'}
          </div>
          ${!repos.length
            ? '<p class="dim" style="font-size:13px">（未找到相关仓库）</p>'
            : repos.map(repo => `
                <div style="display:flex;align-items:center;gap:8px;
                            padding:7px 10px;background:var(--bg3);
                            border-radius:6px;margin-bottom:4px;font-size:13px">
                  <span style="flex:1">
                    <a href="${repo.url||'#'}" target="_blank"
                       style="color:var(--primary-h);text-decoration:none">
                      ${repo.name || '-'}
                    </a>
                    <span class="dim" style="margin-left:8px">
                      ${(repo.description || '').slice(0, 50)}
                    </span>
                  </span>
                  <span class="dim">⭐${(repo.stars||0).toLocaleString()}</span>
                  <span class="badge badge-grey">${repo.language || '-'}</span>
                </div>
              `).join('')
          }
        </div>
      `);
    });
    return sec;
  },
};

/* ══ 启动 ════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => App.init());