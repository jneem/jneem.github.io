---
layout: post
title: "Part 3: Graggles can have cycles"
---

Almost two years ago, I promised a series of three posts about version control.
The first two
([here]({{ site.baseurl }}{% post_url 2017-05-08-merging %})
and [here]({{ site.baseurl }}{% post_url 2017-05-13-pijul %}))
introduced a new (at the time)
framework for version control. The third post, which I never finished, was
going to talk about the datastructures and algorithms used in
[pijul](https://pijul.com), a version control system built around that new
framework. The problem is that pijul is a complex piece of software, and so I
had lots of trouble wrapping my head around it.

Two years later, I'm finally ready to continue with this series of posts (but
having learned from my earlier mistakes, I'm not going to predict the total
number of posts ahead of time). In the meantime, I've written my own toy
version control system (VCS) to help me understand what's going on. It's called
[`ojo`](https://github.com/jneem/ojo), and it's extremely primitive: to start
with, it can only track a single file. However, it is (just barely)
sophisticated enough to demonstrate the important ideas. I'm also doing my best
to make the code is clear and well-documented.

# Graggles can have cycles

As I try and ease back into this whole blogging business, let me just start
with a short answer for something that several people have asked me (and which
also confused me at some point). Graggles (which, as described in the earlier
posts are a kind of generalized file in which the lines are not necessarily
ordered, but instead form a directed graph) are not
[DAGs](https://en.wikipedia.org/wiki/Directed_acyclic_graph); that is, they can
have cycles. To see why, suppose we start out with this graggle

```tikz
DAGLE (0, 0) original
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 1 POS 2/2 * garbage
```

The reason this thing isn't a file is because there's no prescribed order
between the "shoes" line and the "garbage" line. Now suppose that my wife and I
independently flatten this graggle, but in different ways (because apparently
she doesn't care if I get my feet wet).

```tikz
DAGLE (0, 25) original
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 1 POS 2/2 * garbage

FILE (60, 0) mine
to-do
* shoes
* garbage

FILE (60, 50) wife's
to-do
* garbage
* shoes

EDGES
a1 b1
a2 b2
a3 b3
a1 c1
a2 c3
a3 c2
```

Merging these two flattenings will produce the following graggle:

```tikz
DAGLE (0, 0) merged
PARENT 0 POS 1/1 to-do
PARENT 1/3 POS 2/1 * shoes
PARENT 1/2 POS 2/2 * garbage
```

Notice the cycle between "shoes" and "garbage!"

Although I was surprised when I first noticed that graggles could have cycles, if
you think about it a bit more then it makes a lot of sense: one graggle put a
"garbage" dependency on "shoes" and the other put a "shoe" dependency on "garbage,"
and so when you merge them a cycle naturally pops out.

