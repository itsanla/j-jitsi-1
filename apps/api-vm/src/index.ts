import { Hono } from 'hono'

const app = new Hono()

const payload = {
  deployment: 'vercel',
  platform: 'Vercel Serverless Functions',
  runtime: 'Node.js',
  architecture: 'Lambda (AWS)',
  execution_model: 'serverless-function',
  cold_start_estimate: '100ms–1000ms',
  isolation: 'process-container',
}

app.get('/', (c) => c.json({ ...payload, timestamp: new Date().toISOString() }))

export default app
