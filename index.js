const express = require('express');
const { Twilio } = require('twilio');

const app = express();
app.use(express.urlencoded({ extended: true }));

const twilioClient = new Twilio(process.env.TWILIO_SID, process.env.TWILIO_TOKEN);

app.post('/webhook', async (req, res) => {
  const from = req.body.From;

  try {
    await twilioClient.messages.create({
      from: process.env.TWILIO_WHATSAPP_NUMBER,
      to: from,
      body: '🤖 BOT IS WORKING – WEBHOOK OK! AI will be back in 1 minute.'
    });
    console.log('Dummy reply sent to ' + from);
    res.send('');
  } catch (err) {
    console.error(err);
    res.send('');
  }
});

const port = process.env.PORT || 3000;
app.listen(port, () => console.log(`Dummy bot running on port ${port}`));
