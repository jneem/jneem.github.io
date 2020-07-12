---
layout: post
title: "nnnoiseless: porting audio code from C to rust"
---

I ported a C library to rust last week, and it went pretty smoothly. This is
the story, and [here](https://github.com/jneem/nnnoiseless) is the repo.

The library in question is [RNNoise](https://github.com/xiph/rnnoise), a
library for removing noise from audio. It works well, it runs fast, and best of
all it has no knobs that you need to tune. There's even a [rust
binding](https://github.com/RustAudio/rnnoise-c).

So why bother porting it?
Well, I need to patch it so that it would compile with MSVC, but my PR went
unnoticed for a month. I thought about maintaining my own fork, but it's been
more than 10 years since I last wrote anything in C or C++.
And that's how I ended up porting RNNoise to rust. It probably wasn't the most
efficient use of my time, but I had fun and learned something.

There's a lot of information out there about porting C to rust, but the most
useful resource for me was the fantastic
[talk](https://github.com/carols10cents/rust-out-your-c-talk) by Carol (Nichols
|| Goulding). It lays out a simple process for porting one function
at a time: first, you set up the cargo to compile as a static library and you
set up the C build system to link that static library into the C library
(see the slides for the relevant Makefile and Cargo.toml snippets).
Then you can port one function at time: the C code goes like this:

```c
+extern void _celt_lpc(opus_val16 *_lpc, const opus_val32 *ac, int p);
+void __celt_lpc(opus_val16 *_lpc, const opus_val32 *ac, int p)
-void _celt_lpc(opus_val16 *_lpc, const opus_val32 *ac, int p)
{
    /* C body of _celt_lpc */
}
```

and the rust code goes like this:

```rust
+#[no_mangle]
+pub extern "C" fn _celt_lpc(lpc: *mut f32, ac: *const f32, p: c_int) {
+    unsafe {
+        let lpc_slice = std::slice::from_raw_parts_mut(lpc, p as usize);
+        let ac_slice = std::slice::from_raw_parts(ac, p as usize + 1);
+        rs_celt_lpc(lpc_slice, ac_slice);
+    }
+}
+
+fn rs_celt_lpc(lpc: &mut [f32], ac: &[f32]) {
+// rust body of celt_lpc
+}
```

If you've watched the talk (which you should), you might notice that this is a
tiny bit different from what they recommend: I've renamed the original C
function instead of deleting it. I found that this helped me narrow down porting
mistakes, because it made it easy to switch back and forth between the C and
rust implementations.

# Pain points

Most of the porting process was mechanical and easy. One of the less fun parts was
porting code involving C structs. RNNoise has structs that (when ported to
rust) look like this:

```rust
#[repr(C)]
struct RnnState {
    model: *const RnnModel,
    // Various buffers, whose sizes are determined by some subfields of `model`.
    vad_gru_state: *mut f32,
    noise_gru_state: *mut f32,
    denoise_gru_state: *mut f32,
}
```

An idomatic rust version might look something like
```rust
struct RnnState {
    model: &'static RnnModel,
    vad_gru_state: Vec<f32>,
    noise_gru_state: Vec<f32>,
    denoise_gru_state: Vec<f32>,
}
```
but this isn't layout-compatible with the original C version, and so I need to
stick with the original struct for as long as `RnnState` is being accessed by
both C and rust code. This increases the amount of `unsafe` sprinkled around
the rust code, and it was also the source of an annoying bug of the sort that I
thought I had left behind by moving to rust.

# A Heisenbug

At some point during the porting process, my tests started failing in release mode,
but not in debug mode. Most likely some undefined behavior triggered by my amateurish
attempts at unsafe code, but I couldn't quickly spot the problem and the prospect of
a more careful round of debugging didn't spark a whole lot of joy. So I did something
that I never would have dared to do in my C/C++ days: I ignored the problem and kept
porting; after all, the tests were still working in debug mode. And sure enough,
a few more ported functions later and `rustc` found the problem for me: in a function
taking a `&RnnState` parameter, I was modifying data in the `vad_gru_state` buffer.
Since I was using unsafe code, `rustc` didn't complain at first. But once I ported
the `RnnState` struct to safe and idiomatic rust, the compiler flagged the problem
immediately.

# Performance

After getting everything to 100% safe (if not particulary idiomatic) rust, it was time
to check whether performance had suffered.

![initial benchmark](../images/ported_benchmark.svg)

Yes, apparently, by about 50%. The most obvious culprit was bounds checking: there was
a lot of indexing in the C code, and some of it wasn't trivial to convert to a more
rust-friendly, iterator-based version. First priority was the neural network evaluation:

```rust
let m = ...; // At most 114.
let n = ...; // At most 96.

for i in 0..n {
    let output[i] = layer.bias[i] as f32;
    for j in 0..m {
        output[i] += layer.input_weights[j * n + i] as f32 * input[j];
    }
}
```

I can already see you shaking your head. I'm doing naive matrix-vector multiplication
with a 100x100ish matrix in
[column-major format](https://en.wikipedia.org/wiki/Row-_and_column-major_order)?
Not only is this costing me bounds checks, it's terrible for memory locality.
Swapping the weights storage from column- to row-major order only made things
about 1.5% faster, but more importantly it made the whole thing iterator-friendly.
Converting to zips and sums bought another 15%, leaving me only about 25-30% slower
than the C code.

```rust
for i in 0..n {
    let output[i] =
        layer.bias[i] as f32 + 
        layer.input_weights[(i * m)..((i + 1) * m)]
            .iter()
            .zip(input)
            .map(|(&x, &y)| x as f32 * y)
            .sum();
}
```

For my next optimization opportunity, I moved on to the function
that
computes [cross-correlations](https://en.wikipedia.org/wiki/Cross-correlation).
The un-optimized version of this function looks like

```rust
fn pitch_xcorr(xs: &[f32], ys: &[f32], xcorr: &mut [f32]) {
    for i in 0..xcorr.len() {
        xcorr[i] = xs.iter().zip(&ys[i..]).map(|(&x, &y)| x * y).sum();
    }
}
```

but the C code contained a massive, manually-unrolled version. I'd skipped
it while porting, but maybe I'd gain something from porting it over. Here's
an abbreviated version of the optimized function, assuming that all
lengths are a multiple of 4 (the real code also handles the case that they aren't).

```rust
for i in (0..xcorr.len()).step_by(4) {
    let mut c0 = 0.0;
    let mut c1 = 0.0;
    let mut c2 = 0.0;
    let mut c3 = 0.0;

    let mut y0 = ys[i + 0];
    let mut y1 = ys[i + 1];
    let mut y2 = ys[i + 2];
    let mut y3 = ys[i + 3];

    for (x, y) in xs.chunks_exact(4).zip(ys[(i + 4)..].chunks_exact(4)) {
        c0 += x[0] * y0;
        c1 += x[0] * y1;
        c2 += x[0] * y2;
        c3 += x[0] * y3;

        y0 = y[0];
        c0 += x[1] * y1;
        c1 += x[1] * y2;
        c2 += x[1] * y3;
        c3 += x[1] * y0;

        y1 = y[1];
        c0 += x[2] * y2;
        c1 += x[2] * y3;
        c2 += x[2] * y0;
        c3 += x[2] * y1;

        y2 = y[2];
        c0 += x[3] * y3;
        c1 += x[3] * y0;
        c2 += x[3] * y1;
        c3 += x[3] * y2;

        y3 = y[3];
    }
}
```

Basically, both inner and outer loops have been unrolled four times, and I've
exploited the inner loop's unrolling to optimize the memory access pattern.
Thanks to the amazing [`cargo asm`](https://github.com/gnzlbg/cargo-asm), I
can happily report that there's no bounds-checking in the inner loop and that
all the arithmetic has been [auto-vectorized](https://en.wikipedia.org/wiki/Automatic_vectorization)
to work four `f32`s at a time. (Maybe it would get even faster if I unrolled 8 times and
compiled with AVX enabled; I haven't tried that yet.)

This change more than doubled the speed of `pitch_xcorr`, and gained me about 10% overall.
More importantly, it showed me how to coerce the compiler into auto-vectorizing something
that it hadn't auto-vectorized before. I went back to the neural network code and
replaced things like

```rust
xs.iter().zip(ys).map(|(&x, &y)| x as f32 * y).sum()
```

with things like

```rust
{
    let mut sum0 = 0.0;
    let mut sum1 = 0.0;
    let mut sum2 = 0.0;
    let mut sum3 = 0.0;

    for (x, y) in xs.chunks_exact(4).zip(ys.chunks_exact(4)) {
        sum0 += x[0] * y[0];
        sum1 += x[1] * y[1];
        sum2 += x[2] * y[2];
        sum3 += x[3] * y[3];
    }
    sum0 + sum1 + sum2 + sum3
}
```

for another 20% improvement.

Current score: the rust version (still 100% safe) is about 15% faster, and there's probably plenty more
still on the table.

![final benchmark](../images/ported_benchmark_after.svg)

The performance lesson I learned from this is that bounds checking can be expensive in numerical code
and iterator-style code can help a bit, but if you really want faster numerical code then you need
to write in a style that the auto-vectorizer likes. (Or you could use the [SIMD intrinsics](https://doc.rust-lang.org/core/arch/index.html)
directly, but that's another story.)

# A huge thank you to `cargo`

Like I wrote above, it's been a while since I did any C/C++, and because of that I've started to take tools
like cargo for granted. This little porting project brought back some memories, mostly because about half of the
code in RNNoise was actually "vendored" from [opus](https://gitlab.xiph.org/xiph/opus). I put "vendored"
in quotes because I usually think of vendoring as involving a subdirectory (maybe even a git submodule if
I'm lucky) with its own build artifacts. That's not what's going on here, though; I'm just talking about files
that were copied from the source directory of one project to the source directory of another, complete with
never-used functions and never-def'ed ifdefs. The thing is, though, that I understand exactly why they did it:
it's by far the easiest way to share code between C projects. So I just want to finish by saying a big "thank you"
to `cargo` and `crates.io` for making me not have to deal with C dependency management any more.

