import numpy as np

HOP = 256
FFT = 2 * HOP


class LinearEchoCanceller:
    def __init__(self, partitions: int = 16, mu: float = 0.25, ref_gain: float = 1.0, delay: int = 1600, floor: float = 0.0, peak_track: bool = False, smooth: float = 0.9, guard: float = 0.0):
        self.partitions = partitions
        self.floor = floor
        self.guard = guard
        self.peak_track = peak_track
        self.smooth = smooth
        self.mu = mu
        self.ref_gain = ref_gain
        self.weights = np.zeros((partitions, HOP + 1), dtype=np.complex128)
        self.history = np.zeros((partitions, HOP + 1), dtype=np.complex128)
        self.power = np.full(HOP + 1, 1e-3)
        self.ref_prev = np.zeros(HOP)
        self.mic_queue = np.zeros(delay, dtype=np.float64)
        self.mic_pending = np.zeros(0)
        self.ref_pending = np.zeros(0)

    def step(self, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:
        spectrum = np.fft.rfft(np.concatenate([self.ref_prev, ref]))
        self.ref_prev = ref
        self.history = np.roll(self.history, 1, axis=0)
        self.history[0] = spectrum
        estimate = np.fft.irfft((self.weights * self.history).sum(axis=0))[HOP:]
        error = mic - estimate
        if self.guard and float(np.dot(error, error)) > self.guard * float(np.dot(mic, mic)) + 1e4:
            self.weights *= 0.5
            return mic
        error_spectrum = np.fft.rfft(np.concatenate([np.zeros(HOP), error]))
        instant = (np.abs(self.history) ** 2).sum(axis=0)
        smoothed = self.smooth * self.power + (1 - self.smooth) * instant
        self.power = np.maximum(instant, smoothed) if self.peak_track else smoothed
        gradient = np.conj(self.history) * error_spectrum / (self.power + self.floor * float(self.power.mean()) + 1e-3)
        constrained = np.fft.irfft(gradient, axis=1)
        constrained[:, HOP:] = 0
        self.weights += self.mu * np.fft.rfft(constrained, axis=1)
        return error

    def process(self, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:
        delayed = np.concatenate([self.mic_queue, mic.astype(np.float64)])
        self.mic_queue = delayed[len(mic):]
        self.mic_pending = np.concatenate([self.mic_pending, delayed[:len(mic)]])
        self.ref_pending = np.concatenate([self.ref_pending, ref.astype(np.float64) * 32768.0 * self.ref_gain])
        count = min(len(self.mic_pending), len(self.ref_pending)) // HOP
        out = [self.step(self.mic_pending[i * HOP:(i + 1) * HOP], self.ref_pending[i * HOP:(i + 1) * HOP]) for i in range(count)]
        self.mic_pending = self.mic_pending[count * HOP:]
        self.ref_pending = self.ref_pending[count * HOP:]
        return np.clip(np.concatenate(out), -32768, 32767).astype(np.int16) if out else np.zeros(0, dtype=np.int16)
