// ESP32 Kids — AI 代理 (Cloudflare Worker)
//
// 作用：网页把"孩子的自然语言需求"发到这里，Worker 带上 GEMINI_API_KEY 调 Gemini，
// 生成 MicroPython 代码返回给网页。
//
// 安全要点：
//   - GEMINI_API_KEY / CLASS_PASSCODE 都是 Cloudflare 密钥(secret)，只存在这里，网页永远看不到。
//   - CORS 锁定到你的 GitHub Pages 域名，别的网站的脚本调不动它。
//   - 可选班级口令：设了 CLASS_PASSCODE 后，网页必须带对口令才放行。

const ALLOWED_ORIGIN = "https://ahuamao.github.io";
const DEFAULT_MODEL = "gemini-2.5-flash";
const MAX_PROMPT = 2000;

const SYSTEM_PROMPT = `你是帮小朋友把想法变成 ESP32-S3 开发板程序的助手。
运行环境：ESP32-S3 开发板，跑 MicroPython 1.28。
硬性要求：
- 只输出可直接运行的 MicroPython 代码，不要任何解释文字，不要 markdown 代码围栏。
- 用 machine 模块控制硬件（Pin / PWM / ADC 等）、time 模块做延时。
- 多用 print() 把正在做什么告诉小朋友（这些字会显示在他们的屏幕上）。
- 尽量用"有限次数"的循环（例如闪烁 10 次）。不要写没有出口的 while True 死循环，
  因为目前还没有"停止"按钮，死循环会让板子卡住，只能手动按 RST 重启。
- 需求不清楚时，就采用最合理的默认做法，并用 print 说明你的假设。
- 板载 LED 常见在 GPIO 2；不确定引脚时就用它，并 print 一句提示小朋友可以改。`;

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    if (request.method !== "POST") return json({ error: "只接受 POST" }, 405, cors);

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "请求格式错误" }, 400, cors);
    }

    const { passcode, prompt } = body || {};

    if (env.CLASS_PASSCODE && passcode !== env.CLASS_PASSCODE) {
      return json({ error: "班级口令不对" }, 401, cors);
    }
    if (!prompt || typeof prompt !== "string") {
      return json({ error: "需求为空" }, 400, cors);
    }
    if (prompt.length > MAX_PROMPT) {
      return json({ error: "需求太长了，简短点说" }, 400, cors);
    }
    if (!env.GEMINI_API_KEY) {
      return json({ error: "服务器还没配置 GEMINI_API_KEY" }, 500, cors);
    }

    const model = env.GEMINI_MODEL || DEFAULT_MODEL;
    const url =
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${env.GEMINI_API_KEY}`;

    const geminiReq = {
      systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.3, maxOutputTokens: 2048 },
    };

    let resp;
    try {
      resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(geminiReq),
      });
    } catch (e) {
      return json({ error: "连不上 Gemini：" + e.message }, 502, cors);
    }

    if (!resp.ok) {
      const detail = (await resp.text()).slice(0, 300);
      return json({ error: "Gemini 返回错误 " + resp.status, detail }, 502, cors);
    }

    const data = await resp.json();
    const text =
      data?.candidates?.[0]?.content?.parts?.map((p) => p.text).join("") || "";
    const code = stripFences(text).trim();

    if (!code) {
      return json(
        { error: "Gemini 没生成代码", detail: JSON.stringify(data).slice(0, 300) },
        502,
        cors
      );
    }

    return json({ code }, 200, cors);
  },
};

// 去掉 ```python ... ``` 之类的 markdown 代码围栏，只留纯代码
function stripFences(s) {
  const m = s.match(/```(?:python|py)?\s*([\s\S]*?)```/i);
  return m ? m[1] : s;
}

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}
