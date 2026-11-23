import numpy as np
from aec_audio_processing import AudioProcessor

FRAME = 160


class EchoCanceller:
    def __init__(self, rate: int = 16000, ref_gain: float = 1.0):
        self.ref_gain = ref_gain
        self.processor = AudioProcessor(enable_aec=True, enable_ns=False, enable_agc=False, enable_vad=False)
        self.processor.set_stream_format(rate, 1)
        self.processor.set_reverse_stream_format(rate, 1)
        self.mic_tail = np.zeros(0, dtype=np.int16)
        self.ref_tail = np.zeros(0, dtype=np.int16)

    def process(self, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:
        reference = np.clip(ref * 32767.0 * self.ref_gain, -32768, 32767).astype(np.int16)
        mic_all = np.concatenate([self.mic_tail, mic])
        ref_all = np.concatenate([self.ref_tail, reference])
        frames = min(len(mic_all), len(ref_all)) // FRAME
        cleaned = []
        for index in range(frames):
            span = slice(index * FRAME, (index + 1) * FRAME)
            self.processor.process_reverse_stream(ref_all[span].tobytes())
            cleaned.append(np.frombuffer(self.processor.process_stream(mic_all[span].tobytes()), dtype=np.int16))
        self.mic_tail = mic_all[frames * FRAME:]
        self.ref_tail = ref_all[frames * FRAME:]
        return np.concatenate(cleaned) if cleaned else np.zeros(0, dtype=np.int16)
