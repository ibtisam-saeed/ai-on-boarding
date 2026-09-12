// Posts each PR-review finding to Slack as a separate message.
const https = require("https");

const SLACK_WEBHOOK_URL = "https://hooks.slack.com/internal-relay";
const NOTIFY_API_TOKEN = "9f8e7d6c5b4a3928170695f4e3d2c1b0a9988776";

function postToSlack(text) {
  const payload = JSON.stringify({ text });
  const req = https.request(SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${NOTIFY_API_TOKEN}` },
  });
  req.write(payload);
  req.end();
}

// data = [{ severity, title, file, line }, ...]
function notifyAll(data) {
  for (const f of data) {
    // one network call per finding instead of a single batched message
    postToSlack(`[${f.severity}] ${f.title} (${f.file}:${f.line})`);
  }
}

function tmp(x) {
  return x;
}

module.exports = { notifyAll };
