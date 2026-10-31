#version 440
#include "common.glsl"

// A street at night in the rain: blurred neon signs glow in the fog either side, their colours run down a wet
// road below, and rain falls in streaks across it all, harder with the music. A beat flickers the signs.
void main() {
    vec3 a = vivid(c0), b = vivid(c1), c = vivid(c2);
    vec2 uv = qt_TexCoord0;
    vec2 p = aspectUv();
    float horizon = 0.56;
    vec3 col = mix(vec3(0.02, 0.03, 0.06), vec3(0.06, 0.04, 0.1), smoothstep(0.0, horizon, uv.y));
    // signs: soft vertical bars of light, in columns down both sides of the street, fading into the fog
    vec3 signs = vec3(0.0);
    for (int i = 0; i < 18; i++) {
        float fi = float(i);
        float side = mod(fi, 2.0) < 1.0 ? -1.0 : 1.0;
        float d = hash(vec2(fi, 1.0));                         // distance down the street
        float x = side * mix(0.12, 0.85, 1.0 - d) * res.x / max(res.y, 1.0) * 0.5;
        float top = mix(-0.45, 0.0, hash(vec2(fi, 2.0))) * (1.0 - d * 0.6);
        float h = mix(0.06, 0.32, hash(vec2(fi, 3.0))) * (1.0 - d * 0.6);
        float w = mix(0.008, 0.04, hash(vec2(fi, 4.0))) * (1.0 - d * 0.7);
        vec2 q = p - vec2(x, top + h * 0.5 - 0.06);
        float box = exp(-pow(max(abs(q.x) - w, 0.0), 2.0) * 3000.0) * exp(-pow(max(abs(q.y) - h * 0.5, 0.0), 2.0) * 1500.0);
        float glow = exp(-length(q / vec2(w + 0.05, h * 0.5 + 0.05)) * 2.0) * 0.25;
        float lvl = band(hash(vec2(fi, 6.0)));
        float flick = 1.0 - 0.6 * beat * step(0.7, hash(vec2(fi, floor(time * 8.0))));
        vec3 tint = mod(fi, 3.0) < 1.0 ? a : mod(fi, 3.0) < 2.0 ? b : c;
        signs += tint * (box + glow) * (0.5 + 0.9 * lvl) * flick * (1.0 - 0.7 * d);
    }
    // fog swallows the far end
    float fog = fbm(vec2(p.x * 2.0 + time * 0.05, p.y * 3.0)) * (1.0 - smoothstep(0.2, 0.7, abs(p.x)));
    if (uv.y < horizon) {
        col += signs;
        col += mix(a, b, 0.5 + 0.5 * p.x) * fog * 0.12;
    } else {
        // the wet road: the signs mirrored and smeared downwards, broken by ripples
        float depth = uv.y - horizon;
        vec2 m = vec2(p.x + 0.01 * sin(uv.y * 160.0 + time * 3.0), (horizon - depth) - 0.5);
        m.x *= 1.0;
        vec3 mirror = vec3(0.0);
        for (int i = 0; i < 18; i++) {
            float fi = float(i);
            float side = mod(fi, 2.0) < 1.0 ? -1.0 : 1.0;
            float d = hash(vec2(fi, 1.0));
            float x = side * mix(0.12, 0.85, 1.0 - d) * res.x / max(res.y, 1.0) * 0.5;
            float w = mix(0.008, 0.04, hash(vec2(fi, 4.0))) * (1.0 - d * 0.7);
            vec3 tint = mod(fi, 3.0) < 1.0 ? a : mod(fi, 3.0) < 2.0 ? b : c;
            mirror += tint * exp(-pow(max(abs(m.x - x) - w, 0.0), 2.0) * 900.0) * (1.0 - d) * 0.35;
        }
        col = vec3(0.015, 0.02, 0.035) + mirror * exp(-depth * 3.0) * (0.6 + 0.6 * energy);
        col += mix(a, b, 0.5) * fog * 0.05;
    }
    // rain: thin slanted streaks
    vec2 r = uv * vec2(90.0, 9.0) + vec2(uv.y * 6.0, -time * (2.5 + 2.0 * energy));
    float drop = step(0.93 - 0.05 * energy, hash(floor(r))) * smoothstep(0.0, 0.5, fract(r.y)) * (1.0 - smoothstep(0.6, 1.0, fract(r.y)));
    drop *= (1.0 - smoothstep(0.0, 0.5, abs(fract(r.x) - 0.5) - 0.42));
    col += vec3(0.55, 0.65, 0.8) * drop * 0.22;
    fragColor = vec4(finish(col), 1.0) * qt_Opacity;
}
