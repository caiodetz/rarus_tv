// Vercel Serverless Function para /api/config
// Mantém compatibilidade e fallback direto na Vercel

let memoryConfig = {
  audioMode: "stream",
  streamUrl: "https://streams.ilovemusic.de/iloveradio17.mp3",
  youtubeId: "5yx6BWlEVcY",
  title: "🎧 Lofi Chillhop 24/7",
  volume: 80,
  isPlaying: true,
  showClock: true,
  updatedAt: Date.now(),
  updatedBy: "vercel"
};

export default function handler(req, res) {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method === 'POST') {
    try {
      const updates = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
      memoryConfig = {
        ...memoryConfig,
        ...updates,
        updatedAt: Date.now()
      };
      return res.status(200).json({ success: true, config: memoryConfig });
    } catch (err) {
      return res.status(400).json({ error: "Invalid JSON" });
    }
  }

  // GET
  return res.status(200).json(memoryConfig);
}
