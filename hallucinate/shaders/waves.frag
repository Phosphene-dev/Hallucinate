#version 440
#include "common.glsl"

// Layered waves of light rolling across the window, like a sea at night: each wave's height along the
// screen follows its part of the spectrum, and the bass makes the swell.
void main() {
    vec3 a = vivid(c0), b = vivid(c1), c = vivid(c2);
    vec2 uv = qt_TexCoord0;                          // y grows downwards
    vec3 col = mix(b * 0.06, a * 0.02, uv.y);
    col += stars(uv * res, 9.0, 0.05, 0.6 + 0.4 * treble) * 0.5 * (1.0 - smoothstep(0.1, 0.55, uv.y));
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        float depth = fi / 4.0;                       // 0 far away, 1 close
        float x = uv.x * (2.0 + 2.5 * depth) + time * (0.12 + 0.1 * depth) + fi * 1.7;
        float bx = uv.x * 0.9 + 0.05 * fi;
        float level = (band(bx - 0.04) + 2.0 * band(bx) + band(bx + 0.04)) * 0.25;
        float height = 0.3 + 0.24 * depth
                     - (0.05 + 0.12 * level) * (0.6 + 0.4 * depth)
                     - 0.04 * bass * (1.0 + depth)
                     + 0.03 * sin(x * 2.3) + 0.02 * sin(x * 5.1 + fi)
                     + 0.03 * (fbm(vec2(x * 0.8, time * 0.1 + fi)) - 0.5);
        float d = uv.y - height;                      // > 0 below the crest
        vec3 tint = mix(mix(a, b, depth), c, 0.3 * level);
        float crest = exp(-abs(d) * (120.0 - 60.0 * depth)) * (0.6 + 0.9 * level + 0.4 * beat);
        float body = smoothstep(0.0, 0.01, d) * exp(-d * (5.0 - 2.0 * depth)) * 0.12;
        col = mix(col, col * 0.55, smoothstep(0.0, 0.02, d) * 0.6);   // nearer waves cover the far ones
        col += tint * (crest + body) * (0.45 + 0.55 * depth);
    }
    fragColor = vec4(finish(col), 1.0) * qt_Opacity;
}
