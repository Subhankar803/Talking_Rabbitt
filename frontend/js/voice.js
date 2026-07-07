/* ============================================================
   voice.js — speech-to-text (mic) and text-to-speech (spoken answers)
   via the browser's native Web Speech API. No audio ever hits the
   server; only the transcribed text is sent to /api/chat.
   ============================================================ */

const VoiceAssistant = (() => {
  let recognition = null;
  let listening = false;

  function isSupported() {
    return "webkitSpeechRecognition" in window || "SpeechRecognition" in window;
  }

  function startListening({ onResult, onEnd, onError }) {
    if (!isSupported()) {
      onError?.("Voice input isn't supported in this browser. Try Chrome or Edge.");
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      onResult?.(transcript);
    };
    recognition.onerror = (event) => onError?.(event.error);
    recognition.onend = () => { listening = false; onEnd?.(); };

    recognition.start();
    listening = true;
  }

  function stopListening() {
    if (recognition && listening) recognition.stop();
  }

  function speak(text) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.02;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
  }

  function stopSpeaking() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }

  return { isSupported, startListening, stopListening, speak, stopSpeaking };
})();
