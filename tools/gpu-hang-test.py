#!/usr/bin/env python3
"""Deliberately hang the Adreno GPU from userspace (stdlib only; runs on the phone as a user in the render group).

  gpu-hang-test.py ok|hang|LOOPS
'ok' draws a trivial shader (control: the headless EGL/GLES pipeline works), 'hang' draws a fragment shader that loops ~2e9 times
so the GPU makes no progress and the msm hangcheck must reset it. A 25 s alarm ends the process if the driver never gives the job back.
EGL surfaceless platform on the msm render node; no compositor involved.
"""
import ctypes as C, os, signal, sys, time
os.environ.setdefault("EGL_PLATFORM", "surfaceless")
mode = sys.argv[1] if len(sys.argv) > 1 else "ok"
signal.alarm(25)
egl = C.CDLL("libEGL.so.1"); gl = C.CDLL("libGLESv2.so.2")
egl.eglGetDisplay.restype = C.c_void_p; egl.eglGetDisplay.argtypes = [C.c_void_p]
egl.eglInitialize.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p]
egl.eglBindAPI.argtypes = [C.c_uint]
egl.eglChooseConfig.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_void_p), C.c_int, C.POINTER(C.c_int)]
egl.eglCreatePbufferSurface.restype = C.c_void_p; egl.eglCreatePbufferSurface.argtypes = [C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
egl.eglCreateContext.restype = C.c_void_p; egl.eglCreateContext.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
egl.eglMakeCurrent.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
gl.glCreateShader.restype = C.c_uint; gl.glCreateProgram.restype = C.c_uint
gl.glShaderSource.argtypes = [C.c_uint, C.c_int, C.POINTER(C.c_char_p), C.c_void_p]
gl.glGetUniformLocation.argtypes = [C.c_uint, C.c_char_p]
gl.glUniform1f.argtypes = [C.c_int, C.c_float]

dpy = egl.eglGetDisplay(None)
major, minor = C.c_int(), C.c_int()
assert egl.eglInitialize(dpy, C.byref(major), C.byref(minor)), "eglInitialize failed"
egl.eglBindAPI(0x30A0)
attr = (C.c_int * 7)(0x3033, 0x1, 0x3040, 0x40, 0x3024, 8, 0x3038)
cfg, n = C.c_void_p(), C.c_int()
assert egl.eglChooseConfig(dpy, attr, C.byref(cfg), 1, C.byref(n)) and n.value, "no EGL config"
surf = egl.eglCreatePbufferSurface(dpy, cfg, (C.c_int * 5)(0x3057, 256, 0x3056, 256, 0x3038))
ctx = egl.eglCreateContext(dpy, cfg, None, (C.c_int * 3)(0x3098, 3, 0x3038))
assert egl.eglMakeCurrent(dpy, surf, surf, ctx), "eglMakeCurrent failed"
gl.glGetString.restype = C.c_char_p
gl.glReadPixels.argtypes = [C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_void_p]
print("renderer:", gl.glGetString(0x1F01).decode(), "| version:", gl.glGetString(0x1F02).decode(), flush=True)

VS = b"#version 300 es\nvoid main(){ vec2 p = vec2(float((gl_VertexID<<1)&2), float(gl_VertexID&2)); gl_Position = vec4(p*2.0-1.0, 0.0, 1.0); }\n"
# a float loop counter stops increasing at 2^24 (f += 1.0 no longer changes it): with a limit above 2^24 the loop never ends at runtime,
# and since the limit is a uniform the compiler cannot fold it (an int loop bound was silently bounded and finished instantly)
FS = b"#version 300 es\nprecision highp float; uniform float nf; out vec4 c; void main(){ float x = gl_FragCoord.x; for (float f = 0.0; f < nf; f += 1.0) { x = sin(x) + 0.5; } c = vec4(fract(x*0.001), 0.25, 0.5, 1.0); }\n"
def sh(kind, src):
    s = gl.glCreateShader(kind); p = C.c_char_p(src)
    gl.glShaderSource(s, 1, C.byref(p), None); gl.glCompileShader(s); return s
prog = gl.glCreateProgram(); gl.glAttachShader(prog, sh(0x8B31, VS)); gl.glAttachShader(prog, sh(0x8B30, FS)); gl.glLinkProgram(prog)
loops = 4 if mode == "ok" else 1e9 if mode == "hang" else float(mode)
loc = gl.glGetUniformLocation(prog, b"nf")
gl.glUseProgram(prog); gl.glUniform1f(loc, C.c_float(loops))
print("uniform n location", loc, "loops", loops, flush=True)
gl.glViewport(0, 0, 256, 256)
px = (C.c_ubyte * 4)()
t = time.time(); gl.glDrawArrays(4, 0, 3)
gl.glReadPixels(100, 100, 1, 1, 0x1908, 0x1401, px)   # reading the result forces the draw to really execute
gl.glFinish()
print(f"{mode}: pixel={list(px)} glFinish returned after {time.time()-t:.2f} s, glGetError=0x{gl.glGetError():x}", flush=True)
