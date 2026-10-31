#version 440
// A neon theme's screen over the whole window (NeonOverlay.qml): faint scanlines, a vignette at the corners, and
// for a moment after the song changes, a glitch of torn magenta and cyan slices. It draws only light and shade
// over the app; it never moves or hides what's under it.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float time;      // seconds
    float scan;      // scanline strength, 0..1
    float glitch;    // 1 just after a song change, falling to 0
    float vignette;  // 0..1
    vec2 res;        // pixel size
    vec4 ca;         // the accent
    vec4 cb;         // the second colour
};

float hash(float n) { return fract(sin(n) * 43758.5453); }

void main() {
    vec2 uv = qt_TexCoord0;
    vec2 px = uv * res;
    // scanlines: one dark line in three
    float line = step(2.0, mod(px.y, 3.0));
    float shade = line * 0.16 * scan;
    // a soft vignette
    vec2 d = uv - 0.5;
    shade += vignette * smoothstep(0.35, 0.85, length(d * vec2(1.0, 1.15))) * 0.45;
    vec3 col = vec3(0.0);
    float light = 0.0;
    if (glitch > 0.001) {
        // a few horizontal slices, picked fresh twenty times a second
        float frame = floor(time * 20.0);
        float row = floor(uv.y * 28.0);
        float r = hash(row * 13.1 + frame * 7.7);
        if (r > 1.0 - 0.22 * glitch) {
            float off = (hash(row + frame) - 0.5) * 0.06 * glitch;
            float band = step(0.5, fract((uv.x + off) * (6.0 + 20.0 * hash(row * 3.3 + frame))));
            col = mix(ca.rgb, cb.rgb, band);
            light = 0.22 * glitch * (0.4 + 0.6 * hash(row * 5.1 + frame * 1.3));
        }
        // an occasional bright tear line
        float tear = abs(uv.y - hash(frame * 2.3));
        light += (1.0 - smoothstep(0.0, 0.004, tear)) * 0.5 * glitch;
        col = mix(col, cb.rgb, (1.0 - smoothstep(0.0, 0.004, tear)));
    }
    // light over (the glitch) or shade (scanlines, vignette)
    float a = max(shade, light);
    vec3 c = light > shade ? col : vec3(0.0);
    fragColor = vec4(c * a, a) * qt_Opacity;
}
