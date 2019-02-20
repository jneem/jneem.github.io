---
layout: post
title: "Part 1: Merging and patches"
---

A [recent paper](https://arxiv.org/abs/1311.3903) suggested a new mathematical
point of view on version control. I first found out about it from `pijul`,
a new version control system (VCS) that is loosely inspired by that paper. But
if you poke around the `pijul` [home page](https://pijul.com/), you won't find
many details about what makes it different from existing VCSes. So I did a bit
of digging, and this series of blog posts is the result.

In the first part (i.e. this one), I'll go over some of the theory developed in
the paper. In particular, I'll describe a way to think about patches and
merging that is guaranteed to never, ever have a merge conflict. In the second
part, I'll show how `pijul` puts that theory into action, and in the third part
I'll dig into `pijul`'s implementation.

Before getting into some patch theory, a quick caveat: any real VCS needs to
deal with a lot of tedious details (directories, binary files, file renaming,
etc.). In order to get straight to the interesting new ideas, I'll be skipping
all that. For the purposes of these posts, a VCS only needs to keep track of
a single file, which you should think of as a list of lines.

# Patches

A patch is the difference between two files. Later in this series we'll be
looking at some wild new ideas, so let's start with something familiar and
comforting. The kind of patches we'll discuss here go back to the early days of
Unix:

- a patch works line-by-line (as opposed to, for example, word-by-word); and
- a patch can add new lines, but not modify existing lines.

In order to actually have a useful VCS, you need to be able to delete lines
also. But deleting lines turns out to add some complications, so we'll deal
with them later.

For an example, let's start with a simple file: my to-do list for this morning.

```tikz
FILE (0, 0)
to-do list:
* put on shoes
```

Looking back at the list, I realize that I forgot something important. Here's the new one:

```tikz
FILE (0, 0)
to-do list:
* put on socks
* put on shoes
```

To go from the original to-do list to the new one, I added the line with the
socks. In the format of the original Unix "diff" utility, the patch would look like this:

```tikz
FILE (0, 0)
1a2
> * put on socks
```

The "1a2" line is a code saying that we're going to add something after line 1 of the
input file, and the next bit is obviously telling us what to insert.

Since this blog isn't a command line tool, we'll represent patches with pretty diagrams
instead of flat files. Here's how we'll draw the patch above:

```tikz
FILE (0, 0)
to-do list:
* put on shoes

FILE (50, 0)
to-do list:
* put on socks
* put on shoes

EDGES
a1 b1
a2 b3
```

Hopefully it's self-explanatory, but just in case: an arrow goes from left to
right to indicate that the line on the right is the same as the one on the
left. Lines on the right with no arrow coming in are the ones that got added.
Since patches aren't allowed to re-order the lines, the lines are guaranteed
not to cross.

There's something implicit in our notation that really needs to be said out
loud: for us, <b>a patch is tied to a specific input file</b>. This is the first point
where we diverge from the classic Unix ways: the classic Unix patch that we
produced using "diff" could in principle be applied to *any* input file, and it
would still insert "* put on socks" after the first line. In many cases that
wouldn't be what you want, but sometimes it is.

# Merging

The best thing about patches is that they can enable multiple people to edit
the same file and then merge their changes afterwards. Let's suppose that my
wife also decides to put things on my to-do list: she
takes the original file and adds a line:

```tikz
FILE (0, 0)
to-do list:
* put on shoes

FILE (50, 0)
to-do list:
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b2
```

Now there are two new versions of my to-do list: mine with the socks, and my
wife's with the garbage. Let's draw them all together:

```tikz
FILE (0, -15) original
to-do list:
* put on shoes

FILE (50, 0) mine
to-do list:
* put on socks
* put on shoes

FILE (50, -30) wife's
to-do list:
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b3
a1 c1
a2 c2
```

This brings us to merging: since I'd prefer to have my to-do list as a single
file, I want to merge my wife's changes and my own. In this example, it's
pretty obvious what the result should be, but let's look at the general problem
of merging. We'll do this slowly and carefully, and our endpoint might be
different from what you're used to.

## Patch composition

First, I need to introduce some notation for an obvious concept: the
*composition* of two patches is the patch that you would get by applying one
patch and then applying the other. Since a "patch" for us also includes the
original file, you can't just compose any two old patches. If `p` is a patch
taking the file `O` to the file `A` and `r` is a patch taking `A` to `B`, then
you can compose the two (but only in one order!) to obtain a patch from `O` to
`B`. I'll write this composition as `pr`: first apply `p`, then `r`.

It's pretty easy to visualize patch composition using our diagrams: to compute
the composition of two paths, just "follow the arrows"

```tikz
FILE (0, 0) O
to-do list:
* put on shoes

FILE (50, 0) A
to-do list:
* put on socks
* put on shoes

FILE (100, 0) B
to-do list:
* put on socks
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b3
b1 c1
b2 c2
b3 c3

EXTRA
\draw[very thick, red, ->, loosely dotted] (a1.east) to [out=0,in=180] (b1.west) to (b1.east) to [out=0,in=180] (c1.west);
\draw[very thick, red, ->, loosely dotted] (a2.east) to [out=0,in=180] (b3.west) to (b3.east) to [out=0,in=180] (c3.west);
```

to get the (dotted red) patch going from `O` to `B`.

## Merging as composition

I'm going to define carefully what a merge is in terms of patch composition.
I'll do this in a very math-professor kind of way: I'll give a precise
definition, followed by some examples, and only afterwards will I explain
why the definition makes sense.
So here's the definition: if `p` and `q` are two different patches
taking the file `O` to the files `A` and `B` respectively, a *merge* of `p` and `q`
is a pair of patches `r` and `s` such that

* `r` and `s` take `A` and `B` respectively to a common output file `M`, and
* `pr = qs`.

We can illustrate this definition with a simple diagram, where the capital
letters denote files, and the lower-case letters are patches going between
them:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, -2) {\tt B};
\node (m) at (4, 0) {\tt M};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (a) -- node[above] {\tt r} ++ (m);
\draw[->] (b) -- node[below] {\tt s} ++ (m);
```

Instead of saying that `pr = qs`, a mathematician (or anyone who wants
to sound fancy) would say that the diagram above *commutes*.

Here is an example of a merge:

```tikz
FILE (0, 0) original
to-do list:
* put on shoes

FILE (50, 15) mine
to-do list:
* put on socks
* put on shoes

FILE (50, -15) wife's
to-do list:
* put on shoes
* take out garbage

FILE (100, 0) merged
to-do list:
* put on socks
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b3
a1 c1
a2 c2
b1 d1
b2 d2
b3 d3
c1 d1
c2 d3
c3 d4
```

And here is an example of something that is not a merge:

```tikz
FILE (0, 0) original
to-do list:
* put on shoes

FILE (50, 15) mine
to-do list:
* put on socks
* put on shoes

FILE (50, -15) wife's
to-do list:
* put on shoes
* take out garbage

FILE (100, 0) merged
to-do list:
* put on socks
* put on shoes
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b3
a1 c1
a2 c2
b1 d1
b2 d2
b3 d3
c1 d1
c2 d4
c3 d5
```

This is not a merge because it fails the condition `pr = qs`: composing the
patches along the top path gives

```tikz
FILE (0, 0) original
to-do list:
* put on shoes

FILE (50, 0) merged
to-do list:
* put on socks
* put on shoes
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b3
```

but composing them along the bottom path gives

```tikz
FILE (0, 0) original
to-do list:
* put on shoes

FILE (50, 0) merged
to-do list:
* put on socks
* put on shoes
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b4
```

Specifically, the two patches disagree on which of the shoes in the final list
came from the original file. This is the real meaning underlying the condition
`pr = qs`: it means that there will never be any ambiguity about which lines
came from where. If you're used to using `blame` or `annotate` commands with
your favorite VCS, you can probably imagine why this sort of ambiguity would be
bad.

## A historical note

Merging patches is an old idea, of course, and so I just want to briefly
explain how the presentation above differs from "traditional" merging:
traditionally, merging was defined by algorithms (of which there are
[many][1]). These algorithms would try to automatically find a good merge; if
they couldn't, you would be asked to supply one instead.

[1]: https://en.wikipedia.org/wiki/Merge_(version_control)#Merge_algorithms

We'll take a different approach: instead of starting with an algorithm, we'll
start with a list of properties that we want a good merge to satisfy. At the end,
we'll find that there's a unique merge that satisfies all these properties
(and fortunately for us, there will also be an efficient algorithm to find it).

# Merges aren't unique

The main problem with merges is that they aren't unique. This isn't a huge
problem by itself: lots of great things aren't unique. The problem is that we
usually want to merge automatically, and an automatic system needs an
unambiguous answer. Eventually, we'll deal with this by defining a special
class of merges (called perfect merges) which will be unique. Before that,
we'll explore the problem with some examples.

## A silly example

Let's start with a silly example, in which our merge tool decides to
add some extra nonsense:

```tikz
FILE (0, 0) original
to-do list:
* put on shoes

FILE (50, 15) mine
to-do list:
* put on socks
* put on shoes

FILE (50, -15) wife's
to-do list:
* put on shoes
* take out garbage

FILE (100, 0) merged
to-do list:
* put on socks
* put on shoes
* take out garbage
* do the hokey pokey

EDGES
a1 b1
a2 b3
a1 c1
a2 c2
b1 d1
b2 d2
b3 d3
c1 d1
c2 d3
c3 d4
```

No sane merge tool would ever do that, of course, but it's still a valid
merge according to our rule in the last section. Clearly, we'll have
to tighten up the rules to exclude this case.

## A serious example

Here is a more difficult situation with two merges that are actually
reasonable:

```tikz
FILE (0, 0) original
to-do list:

FILE (50, 15) mine
to-do list:
* put on shoes

FILE (50, -15) wife's
to-do list:
* take out garbage

FILE (120, 15) merged1
to-do list:
* put on shoes
* take out garbage

FILE (120, -15) merged2
to-do list:
* take out garbage
* put on shoes

EDGES
a1 b1
a1 c1
b1 d1
b2 d2
b1 e1
b2 e3
c1 d1
c2 d3
c1 e1
c2 e2
````

Both of these merges are valid according to our rules above, but you need to
actually know what the lines *mean* in order to decide that the first merge is
better (especially if it's raining outside). Any reasonable automatic merging
tool would refuse to choose, instead requiring its user to do the merge
manually.

The examples above are pretty simple, but how would you decide in general
whether a merge is unambiguous and can be performed automatically? In existing
tools, the details depend on the merging algorithm. Since we started off with
a non-algorithmic approach, let's see where that leads: instead of specifying
explicitly which merges we can do, we'll describe the properties that an ideal
merge should have.

# Perfect merges

The main idea behind the
definition I'm about to give is that it will never cause any regrets. That is,
no matter what happens in the future, we can always represent the history just
as well through the merge as we could using the original branches. Obviously,
that's a nice property to have; personally, I think it's non-obvious why it's
a good choice as the *defining* property of the ideal merge, but we'll get to
that later.

Ok, here it comes. Consider a merge:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, -2) {\tt B};
\node (m) at (4, 0) {\tt M};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (a) -- node[above] {\tt r} ++ (m);
\draw[->] (b) -- node[below] {\tt s} ++ (m);
```

And now suppose that the original creators of patches `p` and `q`
continued working on their own personal branches, which merged sometime in
the future at the file `F`:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, -2) {\tt B};
\node (m) at (4, 0) {\tt M};
\node (n) at (6, 0) {\tt F};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (a) -- node[above] {\tt r} ++ (m);
\draw[->] (b) -- node[below] {\tt s} ++ (m);
\draw[->] (a) -- node[above] {\tt u} ++ (n);
\draw[->] (b) -- node[below] {\tt v} ++ (n);
\draw[->, dotted] (m) -- node[above] {\tt w} ++ (n);
```

We say that the merge `(r, s)` is a *perfect merge* if for *every* possible
choice of the merge `(u, v)`, there is a unique patch `w` so that `u = rw`
and `v = sw`. (In math terms, the diagram commutes.)
We're going to call `w` a *continuation*, since it tells us how to continue
working from the merged file. To repeat, a merge is perfect if for every
possible future, there is a unique continuation.


## A perfect merge

Let's do a few examples to explore the various corners of our definition.
First, an example of a perfect merge:

```tikz
FILE (0, 0) original
to-do list:
* put on shoes

FILE (50, 15) mine
to-do list:
* put on socks
* put on shoes

FILE (50, -15) wife's
to-do list:
* put on shoes
* take out garbage

FILE (100, 0) merged
to-do list:
* put on socks
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b3
a1 c1
a2 c2
b1 d1
b2 d2
b3 d3
c1 d1
c2 d3
c3 d4
```


It takes a bit of effort to actually *prove* that this is a perfect merge;
I'll leave that as an exercise. It's more interesting to see some examples
that fail to be perfect.

## A silly example

Let's start with the silly example of a merge that introduced an unnecessary
line:

```tikz
FILE (0, 0) original
to-do list:
* put on shoes

FILE (50, 15) mine
to-do list:
* put on socks
* put on shoes

FILE (50, -15) wife's
to-do list:
* put on shoes
* take out garbage

FILE (100, 0) merged
to-do list:
* put on socks
* put on shoes
* take out garbage
* do the hokey pokey

EDGES
a1 b1
a2 b3
a1 c1
a2 c2
b1 d1
b2 d2
b3 d3
c1 d1
c2 d3
c3 d4
```

This turns out (surprise, surprise) not to be a perfect merge.
To understand how our definition of merge perfection excludes merges like this,
here is an example of a possible future without a continuation:

```tikz
FILE (0, 0) original
to-do list:
* put on shoes

FILE (50, 15) mine
to-do list:
* put on socks
* put on shoes

FILE (50, -15) wife's
to-do list:
* put on shoes
* take out garbage

FILE (100, 0) merged
to-do list:
* put on socks
* put on shoes
* take out garbage
* do the hokey pokey

FILE (150, 0) future
to-do list:
* put on socks
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b3
a1 c1
a2 c2
b1 d1
b2 d2
b3 d3
c1 d1
c2 d3
c3 d4
b1 e1
b2 e2
b3 e3
c1 e1
c2 e3
c3 e4
```

Since our patches can't delete lines, there's no way to get from `merged`
to `future`.

## A serious example

Here's another example, the case where there is an ambiguity in the order
of two lines in the merged file:

```tikz
FILE (0, 0) original
to-do list:

FILE (50, 15) mine
to-do list:
* put on shoes

FILE (50, -15) wife's
to-do list:
* take out garbage

FILE (100, 0) merged
to-do list:
* take out garbage
* put on shoes

EDGES
a1 b1
a1 c1
b1 d1
b2 d3
c1 d1
c2 d2
````

This one fails to be a perfect merge because there is a future with
no valid continuation: imagine that my wife and I manually created the desired merge.

```tikz
FILE (0, 0) original
to-do list:

FILE (50, 15) mine
to-do list:
* put on shoes

FILE (50, -15) wife's
to-do list:
* take out garbage

FILE (100, 0) merged
to-do list:
* take out garbage
* put on shoes

FILE (150, 0) future
to-do list:
* put on shoes
* take out garbage

EDGES
a1 b1
a1 c1
b1 d1
b2 d3
c1 d1
c2 d2
b1 e1
b2 e2
c1 e1
c2 e3
````

Now what patch (call it `w`) could be put between `merged` and `future` to make
everything commute?
The only possibility is

```tikz
FILE (100, 0) merged
to-do list:
* take out garbage
* put on shoes

FILE (150, 0) future
to-do list:
* put on shoes
* take out garbage

EDGES
a1 b1
a2 b3
a3 b2
```

which isn't a legal patch because patches aren't allowed to swap lines.

## Terminological remarks

If you've been casually reading about pijul, you might have encountered the
word "pushout." It turns out that the pattern we used for defining a perfect
merge is very common in math. Specifically, in category theory, suppose you
have the following diagram (in which capital letters are objects
and lowercase letters are morphisms):

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, -2) {\tt B};
\node (m) at (4, 0) {\tt M};
\node (n) at (6, 0) {\tt F};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (a) -- node[above] {\tt r} ++ (m);
\draw[->] (b) -- node[below] {\tt s} ++ (m);
\draw[->] (a) -- node[above] {\tt u} ++ (n);
\draw[->] (b) -- node[below] {\tt v} ++ (n);
\draw[->, dotted] (m) -- node[above] {\tt w} ++ (n);
```

If for every `u` and `v` there is a unique `w` such that the diagram commutes,
then `(r, s)` is said to be the *pushout* of `(p, q)`. In other words, what we
called a "perfect merge" above could also be called a "pushout in the category
with files as objects and patches as morphisms."
For most of this article, we'll ignore the general math terminology in favor
of language that's more intuitive and specific to files and patches.


# Conflicts and graggles

The main problem with perfect merges is that they don't always exist. In fact,
we already saw an example:

```tikz
FILE (0, 0) original
to-do list:

FILE (50, 15) mine
to-do list:
* put on shoes

FILE (50, -15) wife's
to-do list:
* take out garbage

EDGES
a1 b1
a1 c1
````

The pair of patches above has no perfect merge. We haven't actually proved it,
but intuitively it's pretty clear, and we also discussed earlier why one
potential merge fails to be perfect. Ok, so not every pair of patches can be
merged perfectly. You probably knew that already, since that's where merge
conflicts come from: the VCS doesn't know how to merge patches on its own, so
you need to manually resolve some conflicts.

Now we come to the coolest part of the paper: a totally different idea for
dealing with merge conflicts. The critical part is that instead of making do
with an imperfect merge, we enlarge the set of objects that the merge can
produce. That is, not every pair of patches can be perfectly merged to
a *file*, but maybe they can be merged to something else.
This idea is extremely common in math, and there's even some general abstract
nonsense showing that it can always be done: there's an abstract way to
generalize files so that every pair of patches of generalized files can be
perfectly merged. The miraculous part here is that in this particular case,
the abstract nonsense condenses into something completely explicit and manageable.

## Graggles

A file is an ordered list of lines. A *graggle*<sup>[1](#footnote1)</sup>
(a mixture of "graph" and "file")
is a directed graph of lines. (Yes, I know it's
a terrible name, but it's better than "object in the free finite cocompletion
of the category of files and patches," which is what the paper calls it.)
In other words, whereas a file insists on having its lines in a strict linear order,
a graggle allows them to be any directed graph. It's pretty easy to see how relaxing
the strict ordering of lines solves our earlier merging issues.
For example, here's a perfect merge of the sort that caused us problems before:

```tikz
FILE (0, 0) original
to-do
* work

FILE (50, 15) mine
to-do
* shoes
* work

FILE (50, -15) wife's
to-do
* garbage
* work

DAGLE (100, 0) merged
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 1 POS 2/2 * garbage
PARENT 2/3 POS 3/1 * work

EDGES
a1 b1
a2 b3
a1 c1
a2 c3
b1 d1
b2 d2
b3 d4
c1 d1
c2 d3
c3 d4
````

In retrospect, this is a pretty obvious solution: if we don't know what order
shoes and garbage should go in, we should just produce an output that doesn't
specify the order. What's a bit less obvious (but is proved in the paper)
is that when we work in the world of graggles instead of the world of files,
*every* pair of patches has a unique perfect merge. What's even cooler is
that the perfect merge is easy to compute. I'll describe it in a second,
but first I have to say how patches generalize to graggles.

A patch between two graggles (say, `A` and `B`) is a function (call it `p`) from
the lines of `A` to the lines of `B` that respects the partial order, in the
sense that if there is a path from `x` to `y` in `A` then there is a path from
`p(x)` to `p(y)` in `B`. (This condition is an extension of the fact that
a patch between two files isn't allowed to change the order.)
Here's an example:

```tikz
DAGLE (0, 0)
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 1 POS 2/2 * garbage
PARENT 2/3 POS 3/1 * work

DAGLE (50, 0)
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * socks
PARENT 2 POS 3/1 * shoes
PARENT 2 POS 3/2 * garbage
PARENT 4 POS 4/2 * dishes
PARENT 3/4 POS 5/1 * work

EDGES
a1 b1
a2 b3
a3 b4
a4 b6
```

## The perfect merge

And now for the merge algorithm: let's say we have a patch `p` going from the
graggle `A` to the graggle `B` and another patch `q` going from `A` to `C`. To
compute the perfect merge of `p` and `q`,

1. write down the graggles `B` and `C` next to each other, and then
2. whenever a line in `B` and a line in `C` share a "parent" in `A`, collapse them into a single line.

That's it: two steps. Here's the algorithm at work on our previous example: we
want to merge these two patches:

```tikz
FILE (0, 0) original
to-do
* work

FILE (50, 15) mine
to-do
* shoes
* work

FILE (50, -15) wife's
to-do
* garbage
* work

EDGES
a1 b1
a2 b3
a1 c1
a2 c3
````

So first, we write down the two to-be-merged files next to each other:

```tikz
FILE (0, 15) mine
to-do
* shoes
* work

FILE (0, -15) wife's
to-do
* garbage
* work

DAGLE (50, 0) merge in progress
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 2 POS 3/1 * work
PARENT 0 POS 1/2 to-do
PARENT 4 POS 2/2 * garbage
PARENT 5 POS 3/2 * work

EDGES
a1 c1
a2 c2
a3 c3
b1 c4
b2 c5
b3 c6
```

For the second step, we see that both of the "to-do" lines came from the same
line in the original file, so we combine those two into one. After doing the
same to the "work" lines, we get the desired output:

```tikz
FILE (0, 15) mine
to-do
* shoes
* work

FILE (0, -15) wife's
to-do
* garbage
* work

DAGLE (50, 0) merged
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 1 POS 2/2 * garbage
PARENT 2/3 POS 3/1 * work

EDGES
a1 c1
a2 c2
a3 c4
b1 c1
b2 c3
b3 c4
```

## Working with graggles.

By generalizing files to graggles, we got a very nice benefit: every pair of
patches has a (unique) perfect merge, and we can compute it easily. But there's
an obvious flaw: all the tools that we use (editors, compilers, etc.) work on
files, not graggles. This is where the paper stops providing guidance, but there
is an easy solution: whenever a merge results in something that isn't a file,
just make a new patch that turns it into a file. We'll call this *flattening*,
and here's an example:

```tikz
FILE (0, 0) original
to-do
* work

FILE (50, 15) mine
to-do
* shoes
* work

FILE (50, -15) wife's
to-do
* garbage
* work

DAGLE (100, 0) merged
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 1 POS 2/2 * garbage
PARENT 2/3 POS 3/1 * work

FILE (150, 0) flattened
to-do
* shoes
* garbage
* work


EDGES
a1 b1
a2 b3
a1 c1
a2 c3
b1 d1
b2 d2
b3 d4
c1 d1
c2 d3
c3 d4
d1 e1
d2 e2
d3 e3
d4 e4
```

## That looks like a merge conflict!

If your eyes haven't glazed over by now (sorry, it's been a long post), you
might be feeling a bit cheated: I promised you a new framework that avoids the
pitfalls of manual merge resolution, but flattening looks an awful lot like
manual merge resolution. I'll answer this criticism in more detail in the next
post, where I demonstrate the `pijul` tool and how it differs from `git`. But
here's a little teaser: the difference between flattening and manual merge
resolution is that flattening is completely transparent to the VCS: it's just
a patch like any other. That means we can do fun things, like re-ordering or
reverting patches, even in the presence of conflicting merges. More on that
in the next post.

# Deleting lines

It's time to finally address something I put off way at the beginning of the
post: the system I described was based on patches that can't delete lines, and
we obviously need to allow deletions in any practical system. Unfortunately,
the paper doesn't help here: it claims that you can incorporate deletion into
the system I described without really changing anything, but there's a bug in
the paper. Specifically, if you tweak the definitions to allow deletion then
the category of graggles turns out not to be closed under pushouts any more.
Here's an example where the merge algorithm in the paper turns out not to be
perfect:

```tikz
DAGLE (0, 0) original
PARENT 0 POS 1/1 three
PARENT 0 POS 2/1 unordered
PARENT 0 POS 3/1 lines

DAGLE (40, 20) branch1
PARENT 0 POS 1/1 three
PARENT 1 POS 2/1 unordered
PARENT 0 POS 3/1 lines

DAGLE (40, -20) branch2
PARENT 0 POS 1/1 three
PARENT 0 POS 2/1 unordered
PARENT 2 POS 3/1 lines

DAGLE (80, 0) perfect?
PARENT 0 POS 1/1 three
PARENT 1 POS 2/1 unordered
PARENT 2 POS 3/1 lines

DAGLE (150, 0) future
PARENT 0 POS 1/1 three
PARENT 0 POS 2/1 lines

EDGES
a1 b1
a2 b2
a3 b3
a1 c1
a2 c2
a3 c3
b1 d1
b2 d2
b3 d3
c1 d1
c2 d2
c3 d3
b1 e1
b3 e2
c1 e1
c3 e2
```

(Since this post has dragged on long enough, I'll leave it as an exercise to
figure out what the problem is).

## Ghost lines

Fortunately, there's a trick to emulate line deletion in our original patch
system. I got this idea from pijul, but I'll present it in a slightly
different way. The idea is to allow "ghost" lines instead of actually deleting
them. That is, we mark every line in our graggle as either "live" or "ghost."
Then we add one extra rule to our patches: a live line can turn into a ghost
line, but not the other way around. We'll draw ghost lines in gray, and arrows
pointing to ghost lines will be dashed. Here's a patch that deletes the "shoes"
line.

```tikz
DAGLE (0, 0)
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 2 POS 3/1 * garbage

DAGLE (50, 0)
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 GHOST * shoes
PARENT 2 POS 3/1 * garbage

EDGES
a1 b1
a2 b2 dashed
a3 b3
```

The last remaining piece is to extend the perfect merge algorithm to cover
our new graggles with ghost lines. This turns out to be easy; here's the new
algorithm:

1. Write down side-by-side the two graggles to be merged.
2. For every pair of lines with a common parent, "collapse" them into a single line,
  *and if one of them was a ghost, make the collapsed line a ghost*.

The bit in italics is the only new part, and it barely adds any extra complexity.

# Conclusion

I showed you (in great detail) a mathy way of thinking about patches in a VCS,
although I haven't shown a whole lot of motivation for it yet. At the very
least, though, next time someone starts droning on about "patch theory," you'll
have some idea what they're talking about.

In the next post, I'll talk about [pijul](https://pijul.com), a VCS that is loosely
based around the algorithms I described in this post. There you'll get to see
some (toy) examples where pijul's solid mathematical underpinnings help it to
avoid corner cases that trip up some more established VCSes.

# Acknowledgement

I'd like to thank Pierre-Étienne Meunier for his comments and corrections on
a draft of this post. Of course, any errors that remain are my own
responsibility.

<a name="footnote1">1</a>:
An earlier version of this post called them "digles" (for **di**rected
**g**raph fi**le**), but a couple years later I decided that "graggles" sounds a
bit better. Plus, if you
[mispronounce](https://en.wikipedia.org/wiki/Quiscalus) it a little, it fits in
the pijul's whole bird theme.

