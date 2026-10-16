#version 440
#include "common.glsl"

// A ring of light around the middle: each part of it swells with its part of the spectrum, the bass breathes
// it wider, and every beat sends a ripple out across the dark.
void main() {
    vec3 a = vivid(c0), b = vivid(c1), c = vivid(c2);
    vec2 p = aspectUv();
    float r = length(p);
    float ang = atan(p.y, p.x);                      // -pi..pi
    float side = abs(ang) / 3.14159265;              // 0 at the right, 1 at the left: the ring mirrors itself
    float sx = side * 0.92 + 0.02;
    float level = (band(sx - 0.04) + 2.0 * band(sx) + band(sx + 0.04)) * 0.25;   // smoothed, so the ring stays round
    float base = 0.22 + 0.05 * bass + 0.02 * sin(time * 0.6);
    float radius = base + 0.12 * level + 0.015 * (fbm(vec2(ang * 3.0, time * 0.4)) - 0.5);
    float d = r - radius;
    vec3 tint = mix(a, b, smoothstep(0.0, 1.0, side));
    tint = mix(tint, c, 0.35 * level);
    vec3 col = mix(a * 0.025, b * 0.05, smoothstep(0.0, 0.9, r));
    col += stars(qt_TexCoord0 * res, 10.0, 0.05, 0.5 + 0.5 * treble) * 0.6 * smoothstep(0.25, 0.7, r);
    col += tint * exp(-abs(d) * (70.0 - 30.0 * level)) * (0.9 + 0.8 * level + 0.4 * beat);   // the ring
    col += tint * exp(-max(d, 0.0) * 9.0) * smoothstep(0.0, -0.02, -d) * 0.18 * (0.5 + energy); // its glow outward
    col += mix(b, c, 0.5) * exp(-r * 7.0) * (0.12 + 0.25 * bass);                           // a soft core
    for (int i = 0; i < 3; i++) {                                                             // ripples
        float fi = float(i);
        float wave = fract(time * 0.18 + fi / 3.0);
        float rr = base + wave * 0.75;
        col += c * exp(-abs(r - rr) * 90.0) * (1.0 - wave) * (0.12 + 0.35 * beat);
    }
    fragColor = vec4(finish(col), 1.0) * qt_Opacity;
}
