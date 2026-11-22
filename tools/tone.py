import wave, struct, math, sys
amp = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
w = wave.open("/tmp/tone.wav", "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
w.writeframes(b"".join(struct.pack("<hh", int(amp*math.sin(2*math.pi*440*i/48000)), int(amp*math.sin(2*math.pi*440*i/48000))) for i in range(48000*2)))
w.close(); print("tone written", amp)
