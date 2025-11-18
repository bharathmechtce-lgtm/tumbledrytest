const express = require('express');
const { Twilio } = require('twilio');
const OpenAI = require('openai');

const app = express();
app.use(express.urlencoded({ extended: true }));

const twilioClient = new Twilio(process.env.TWILIO_SID, process.env.TWILIO_TOKEN);

const openai = new OpenAI({
  apiKey: process.env.AZURE_OPENAI_KEY,
  baseURL: `${process.env.AZURE_OPENAI_ENDPOINT}/openai/deployments/${process.env.AZURE_OPENAI_DEPLOYMENT}`,
  defaultQuery: { 'api-version': '2024-08-01-preview' },
  defaultHeaders: { 'api-key': process.env.AZURE_OPENAI_KEY },
});

app.post('/webhook', async (req, res) => {
  const message = req.body.Body?.trim();
  const from = req.body.From;

  if (!message) return res.send('');

  try {
    const completion = await openai.chat.completions.create({
      model: process.env.AZURE_OPENAI_DEPLOYMENT,
      messages: [
        { role: 'system', content: 'You are a fun, helpful WhatsApp assistant.' },
        { role: 'user', content: message }
      ],
    });

    const reply = completion.choices[0].message.content;

    await twilioClient.messages.create({
      from: process.env.TWILIO_WHATSAPP_NUMBER,
      to: from,
      body: reply
    });

    res.send('');
  } catch (error) {
    console.error('AI Error:', error.message);
    res.send('');
  }
});

const port = process.env.PORT || 3000;
app.listen(port, () => console.log(`Real AI WhatsApp Bot live on port ${port}`));
