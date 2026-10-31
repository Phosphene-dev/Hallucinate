#version 440
#include "common.glsl"

// A dark room strung with cables: grey wires sag across it in layers, swaying slowly and shivering with the bass,
// and one pool of light lies on the floor below, breathing with the music. Signals run along the wires as small
// sparks in the theme's colours whenever the highs come in.
float wire(vec2 p, float seed, float sag, float thick) {
    // a cable from one side to the other, hanging in a curve, with a slow sway
    float x = p.x;
    float y0 = mix(-0.55, 0.15, hash(vec2(seed, 1.3)));
    float bend = sag * (1.0 - pow(x * (0.9 + 0.4 * hash(vec2(seed, 2.1))), 2.0));
    float sway = 0.02 * sin(time * (0.3 + 0.3 * hash(vec2(seed, 4.4))) + seed * 6.0) * (1.0 + 2.0 * bass);
    float wob = 0.012 * (noise(vec2(x * 3.0 + seed * 9.0, time * 0.2)) - 0.5);
    float y = y0 + bend + sway + wob;
    return 1.0 - smoothstep(0.0, thick, abs(p.y - y));  // (edges low to high: reversed ones are undefined on some GPUs)
}

void main() {
    vec3 a = vivid(c0), b = vivid(c1);
    vec2 p = aspectUv();
    vec3 col = vec3(0.012, 0.012, 0.016);
    // the floor: a dim plane below the horizon with planks running away
    float horizon = 0.12;
    if (p.y > horizon) {
        float depth = (p.y - horizon);
        float planks = (1.0 - smoothstep(0.0, 0.02, abs(fract(p.x / (depth + 0.05) * 1.2) - 0.5) - 0.47));
        col += vec3(0.03, 0.025, 0.022) * (0.6 + 0.4 * planks) * smoothstep(0.0, 0.4, depth);
    }
    // the pool of light on the floor
    vec2 c = p - vec2(0.0, 0.32);
    float pool = exp(-dot(c * vec2(1.0, 2.8), c * vec2(1.0, 2.8)) * (7.0 - 2.5 * energy));
    col += vec3(0.85, 0.82, 0.75) * pool * (0.35 + 0.35 * energy + 0.2 * beat);
    // the wires, far ones thin and dim, near ones thick
    for (int i = 0; i < 14; i++) {
        float fi = float(i);
        float layer = fi / 14.0;
        float thick = mix(0.0025, 0.009, layer);
        float w = wire(p * vec2(1.0, 1.0 + 0.3 * (1.0 - layer)), fi * 1.7 + 0.3, mix(0.08, 0.3, hash(vec2(fi, 9.0))), thick);
        vec3 grey = vec3(mix(0.16, 0.42, layer)) * (1.0 + 0.6 * pool);
        col = mix(col, grey, w * 0.9);
        // a spark running along it
        float run = fract(time * (0.15 + 0.2 * hash(vec2(fi, 3.3))) + hash(vec2(fi, 7.7)));
        float spark = exp(-abs(p.x - (run * 2.4 - 1.2)) * 40.0) * w;
        col += mix(a, b, hash(vec2(fi, 5.5))) * spark * (0.4 + 2.0 * treble);
    }
    fragColor = vec4(finish(col), 1.0) * qt_Opacity;
}
