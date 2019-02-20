---
layout: post
title: "Part 2: Merging, patches, and pijul"
---

In the [last post]({{ site.baseurl }}{% post_url 2017-05-08-merging %}),
I talked about a mathematical
framework for a version control system (VCS) without merge conflicts. In this
post I'll explore [pijul](pijul.com), which is a VCS based on a similar system.
Note that pijul is under heavy development; this post is based on a development
snapshot (I almost called it a "git" snapshot by mistake), and might be out of
date by the time you read it.

The main goal of this post is to describe how pijul handles what other VCSes
call conflicts. We'll see some examples where pijul's approach works better than
git's, and I'll discuss why.

# Some basics

I don't want to write a full pijul tutorial here, but I do need to mention
the basic commands if you're to have any hope of understanding the rest
of the post. Fortunately, pijul commands have pretty close analogues in
other VCSes.

- `pijul init` creates a pijul repository, much like `git init` or `hg init`.
- `pijul add` tells pijul that it should start tracking a file, much like `git
  add` or `hg add`.
- `pijul record` looks for changes in the working directory and records a patch
  with those changes, so it's similar to `git commit` or `hg commit`. Unlike
  those two (and much like `darcs record`), `pijul record` asks a million
  questions before doing anything; you probably want to use the `-a` option to
  stop it.
- `pijul fork` creates a new branch, like `git branch`. Unlike `git branch`,
  which creates a copy of the current branch, `pijul fork` defaults to creating a copy of
  the master branch. (This is a bug, apparently.)
- `pijul apply` adds a patch to the current branch, like `git cherry-pick`.
- `pijul pull` fetches and merges another branch into your current branch.
  The other branch could be a remote branch, but it could also just be a
  branch in the local repository.

# Dealing with conflicts

As I explained in the last post, pijul differs from other VCSes by not having
merge conflicts. Instead, it has (what I call) *graggles*, which are different
from files in that their lines form a directed acyclic graph instead of
a totally ordered list. The thing about graggles is that you can't really work
with them (for example, by opening them in an editor), so pijul doesn't let you
actually see the graggles: it stores them as graggles internally, but renders them
as files for you to edit. As an example, we'll create a graggle by asking pijul
to perform the following merge:

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

Here are the pijul commands to do this:

```
$ pijul init

# Create the initial file and record it.
$ cat > todo.txt << EOF
> to-do
> * work
> EOF
$ pijul add todo.txt
$ pijul record -a -m todo

# Switch to a new branch and add the shoes line.
$ pijul fork --branch=master shoes
$ sed -i '2i* shoes' todo.txt
$ pijul record -a -m shoes

# Switch to a third branch and add the garbage line.
$ pijul fork --branch=master garbage
$ sed -i '2i* garbage' todo.txt
$ pijul record -a -m garbage

# Now merge in the "shoes" change to the "garbage" branch.
$ pijul pull . --from-branch shoes
```

The first thing to notice after running those commands is that pijul
doesn't complain about any conflicts (this is not intentional; it's
a known issue).
Anyway, if you run
the above commands then the final, merged version of `todo.txt` will
look like this:

```tikz
FILE (0, 0) merged
to-do
* shoes
>>>>>>>>>
* garbage
<<<<<<<<<
* work
```

That's... a little disappointing, maybe, especially since pijul was supposed to
free us from merge conflicts, and this looks a lot like a merge conflict. The
point, though, is that pijul has to somehow produce a file -- one that the
operating system and your editor can understand -- from the graggle that it
maintains internally. The output format just happens to look a bit like what
other VCSes output when they need you to resolve a merge conflict.

As it stands, pijul doesn't have a very user-friendly way to actually see
its internal graggles. But with a little effort, you can figure it out. The
secret is the command

```
RUST_LOG="libpijul::backend=debug" pijul info --debug
```

For every branch, this will create a file named `debug_<branchname>` which
describes, in graphviz's `dot` format, the graggles contained in that branch.
That file's a bit hard to read since it doesn't directly tell you the actual
contents of any line; in place of, for example, "to-do", it just has
a giant hex string corresponding to pijul's internal identifiers for that line.
To decode everything, you'll need to look at the terminal output of that
pijul command above. Part of it should look like this:

```
DEBUG:libpijul::backend::dump: ============= dumping Contents
DEBUG:libpijul::backend::dump: > Key { patch: PatchId 0x0414005c0c2122ca, line: LineId(0x0200000000000000) } Value (0) { value: [Ok("")] }
DEBUG:libpijul::backend::dump: > Key { patch: PatchId 0x0414005c0c2122ca, line: LineId(0x0300000000000000) } Value (12) { value: [Ok("to-do\n")] }
```

By cross-referencing that output with the contents of `debug_<branchname>`,
you can reconstruct pijul's internal graggles.
Just this once, I've done it for you, and the result is exactly as it should be:

```tikz
DAGLE (100, 0) merged
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 1 POS 2/2 * garbage
PARENT 2/3 POS 3/1 * work
```

## What should I do with a conflict?

Since pijul will happily work with graggles internally, you could in principle
ignore a conflict and work on other things. That's probably a bad idea for
several reasons (for starters, there are no good tools for working with graggles,
and their presence will probably break your build). So here's my unsolicited
opinion: when you have a conflict, you should resolve it ASAP.
In the example above, all we need to do is remove the `>>>` and `<<<` lines
and then record the changes:

```
$ sed -i 3D;5D todo.txt
$ pijul record -a -m resolve
```

To back up my recommendation for immediate flattening, I'll give an example
where pijul's graggle-to-file rendering is lossy. Here are two different graggles:

```tikz
DAGLE (0, 0)
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 2 POS 3/1 * work
PARENT 1 POS 3/2 * garbage
PARENT 4 POS 4/2 * shop
PARENT 3/4 POS 4/1 * home

DAGLE (50, 0)
PARENT 0 POS 1/1 to-do
PARENT 1 POS 2/1 * shoes
PARENT 2 POS 3/1 * work
PARENT 1 POS 2/2 * garbage
PARENT 4 POS 3/2 * shop
PARENT 3 POS 4/1 * home
PARENT 5 POS 4/2 * home
```

But pijul renders both in the same way:

```tikz
FILE (0, 0)
to-do
>>>>>>>>>
* shoes
* work
* home
=========
* garbage
* shop
* home
<<<<<<<<<
```

This is a perfectly good representation of the graggle on the right, but it loses
information from the one on the left (such as the fact that both "home" lines
are the same, and the fact that "shop" and "home" don't have a prescribed
order). The good news here is that as long as your graggle came from merging two
*files*, then pijul's rendering is lossless. That means you can avoid the
problem by flattening your graggles to files after every merge (i.e., by
resolving your merge conflicts immediately).
Like [cockroaches](http://www.livescience.com/33995-cockroaches.html),
graggles are important for the ecosystem as a whole, but you should still flatten them
as soon as they appear.


## Case study 1: reverting an old commit

It's (unfortunately) common to discover that an old commit introduced
a show-stopper bug. On the bright side, every VCS worth its salt has some way
of undoing the problematic commit without throwing away everything else you've
written since then. But if the problematic commit predates a merge conflict,
undoing it can be painful.

As an illustration of what pijul brings to the table, we'll look at
a situation where pijul's conflict-avoidance saves the day (at least,
compared to git; darcs also does ok here).
We'll start with the example merge from before, including
our manual graggle resolution:

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

FILE (150, 0) resolved
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
````

Then we'll ask pijul to revert the "shoes" patch:

```
$ pijul unrecord --patch=<hash-of-shoes-patch>
$ pijul revert
```

The result? We didn't have any conflicts while reverting the old patch,
and the final file is exactly what we expected:

```tikz
FILE (150, 0)
to-do
* garbage
* work
```

Let's try the same thing with git:

```
$ git init

# Create the initial file and record it.
$ cat > todo.txt << EOF
> to-do
> * work
> EOF
$ git add todo.txt
$ git commit -a -m todo

# Switch to a new branch and add the shoes line.
$ git checkout -b shoes
$ sed -i '2i* shoes' todo.txt
$ git commit -a -m shoes

# Switch to a third branch and add the garbage line.
$ git checkout -b garbage master
$ sed -i '2i* garbage' todo.txt
$ git commit -a -m garbage

# Now merge in the "shoes" change to the "garbage" branch.
$ git merge shoes
Auto-merging todo.txt
CONFLICT (content): Merge conflict in todo.txt
Automatic merge failed; fix conflicts and then commit the result.
```

That was expected: there's a conflict, so we have to resolve it. So I edited
`todo.txt` and manually resolved the conflict. Then,

```
# Commit the manual resolution.
$ git commit -a -m merge
# Try to revert the shoes patch.
$ git revert <hash-of-shoes-patch>
error: could not revert 4dcf1ae... shoes
hint: after resolving the conflicts, mark the corrected paths
hint: with 'git add <paths>' or 'git rm <paths>'
hint: and commit the result with 'git commit'
```

Since git can't "see through" my manual merge resolution, it can't handle
reverting the patch by itself. I have to manually resolve the conflicting
patches both when applying and reverting.

I won't bore you with long command listings for other VCSes, but you can test
them out yourself! I've tried mercurial (which does about the same as git in
this example) and darcs (which does about the same as pijul in this example).

## A little warning about `pijul unrecord`

I'm doing my best to present roughly equivalent command sequences for pijul and
git, but there's something important you should know about the difference
between `pijul unrecord` and `git revert`: `pijul unrecord` modifies the
history of the repository, as though the unrecorded patch never existed. In
this way, `pijul unrecord` is a bit like a selective version of `git reset`.
This is probably not the functionality that you want, especially if you're
working on a public repository. Pijul actually does have the internal
capability to do something closer to `git revert` (i.e., undo a patch while
keeping it in the history), but it isn't yet user-accessible.

# Sets of patches

The time has come again to throw around some fancy math words. First,
*associativity*. As you might remember, a binary operator (call it `+`)
is associative if `(x + y) + z = x + (y + z)` for any `x`, `y`, and `z`.
The great thing about associative operators is that you never need
parentheses: you can just write `x + y + z` and there's no ambiguity.
Associativity automatically extends to more than three things: there's also
no ambiguity with `w + x + y + z`.

The previous paragraph is relevant to patches because perfect merging
is associative, in the following sense: if I have multiple patches
(let's say three to keep the diagrams manageable) then there's a unique
way to perfectly merge them all together. That three-way merge
can be written as combinations of two-way merges in multiple different
ways, but every way that I write it gives the same result. Let's have some pictures.
Here are my three patches:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, 0) {\tt B};
\node (c) at (2, -2) {\tt C};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (o) -- node[above] {\tt r} ++ (c);
```

And here's one way I could merge them all together:
first, merge patches `p` and `q`:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, 0) {\tt B};
\node (c) at (2, -2) {\tt C};
\node (m) at (4, 1) {\tt M};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (o) -- node[above] {\tt r} ++ (c);
\draw[->] (a) -- node[above] {\tt m} ++ (m);
\draw[->] (b) -- node[above] {\tt n} ++ (m);
```

Then, merge patches `pm` (remember, that's the patch I get from applying `p` and then `m`,
which in the diagram above is the same as `qn`) and `r`:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, 0) {\tt B};
\node (c) at (2, -2) {\tt C};
\node (m) at (4, 1) {\tt M};
\node (n) at (6, 0) {\tt N};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (o) -- node[above] {\tt r} ++ (c);
\draw[->] (a) -- node[above] {\tt m} ++ (m);
\draw[->] (b) -- node[above] {\tt n} ++ (m);
\draw[->] (m) -- node[above] {\tt x} ++ (n);
\draw[->] (c) -- node[above] {\tt y} ++ (n);
```

Another way would be to first merge `q` and `r`, and then merge `p` in to the result:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, 0) {\tt B};
\node (c) at (2, -2) {\tt C};
\node (m) at (4, -1) {\tt M};
\node (n) at (6, 0) {\tt N};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (o) -- node[above] {\tt r} ++ (c);
\draw[->] (b) -- (m);
\draw[->] (c) -- (m);
\draw[->] (m) -- (n);
\draw[->] (a) -- (n);
```

Yet a third way would be to merge `p` and `q`, then merge `q` and `r`, and finally merge
the results of those merges. This one gives a nice, symmetric picture:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 2) {\tt A};
\node (b) at (2, 0) {\tt B};
\node (c) at (2, -2) {\tt C};
\node (m) at (4, 1) {\tt M};
\node (n) at (4, -1) {\tt N};
\node (q) at (6, 0) {\tt Q};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt q} ++ (b);
\draw[->] (o) -- node[above] {\tt r} ++ (c);
\draw[->] (a) -- (m);
\draw[->] (b) -- (m);
\draw[->] (b) -- (n);
\draw[->] (c) -- (n);
\draw[->] (m) -- (q);
\draw[->] (n) -- (q);
```

The great thing about our mathematical foundation from the previous post is
that *all these merges produce the same result*. And I don't just mean that
they give the same final file: they also result in the same patches, meaning
that everyone will always agree on which lines in the final file came from
where. There isn't even anything special about the initial configuration (three
patches coming out of a single file). I could start with an arbitrarily complex
history, and there would be an unambiguous way to merge together all of the
patches that it contains. In this sense, we can say that the current state of
a pijul branch is determined by a set of patches; this is in contrast to most
existing VCSes, where the order in which patches are merged also matters.

## Reordering and antiquing patches

One of the things you might have heard about pijul is that it can reorder
patches (i.e. that they are commutative). This is not 100% accurate, and it
might also be a bit confusing if you paid attention in my last post. That's
because a patch, according to the definition I gave before, *includes its input
file*. So if you have a patch `p` that turns file `A` into file `B` and a patch
`q` that turns file `B` into file `C`, then it makes sense to apply `p` and
then `r` but not the other way around. It turns out that pijul has a nice trick
up its sleeve, which allows you to reorder patches as long as they don't
"depend" (and I'll explain what that means precisely) on each other.

The key idea behind reordering patches is something I call "antiquing."
Consider the following sequenced patches:

```tikz
FILE (0, 0)
to-do list:
* go to work

FILE (50, 0)
to-do list:
* put on shoes
* go to work

FILE (100, 0)
to-do list:
* put on shoes
* go to work
* take out garbage

EDGES
a1 b1
a2 b3
b1 c1
b2 c2
b3 c3
```

According to how we defined patches, the second patch (let's call it the
garbage patch) has to be applied after the first one (the shoes patch). On the
other hand, it's pretty obvious just by staring at them that the garbage patch
doesn't depend on the shoes patch. In particular, the following parallel
patches convey exactly the same information, without the dependencies:

```tikz
FILE (0, 0)
to-do list:
* go to work

FILE (50, 15)
to-do list:
* put on shoes
* go to work

FILE (50, -15)
to-do list:
* go to work
* take out garbage

EDGES
a1 b1
a2 b3
a1 c1
a2 c2
```

How do I know for sure that they convey the same information? Because if we take
the perfect merge of the diagram above then we get back the original sequenced
diagram by following the top path in the merge!

```tikz
FILE (0, 0)
to-do list:
* go to work

FILE (50, 15)
to-do list:
* put on shoes
* go to work

FILE (50, -15)
to-do list:
* go to work
* take out garbage

FILE (100, 0)
to-do list:
* put on shoes
* go to work
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
c2 d2
c3 d4
```

This example motivates the following definition: given a pair of patches
`p` and `q` in sequence:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 0) {\tt A};
\node (b) at (4, 0) {\tt B};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (a) -- node[above] {\tt q} ++ (b);
```

we say that `q` can be *antiqued* if there exists some patch `a(q)` starting at `O`
such that the perfect merge between `p` and `a(q)` involves `q`:

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 0) {\tt A};
\node (b) at (4, 0) {\tt B};
\node (c) at (2, -2) {\tt C};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (a) -- node[above] {\tt q} ++ (b);
\draw[->] (o) -- node[below] {\tt a(q)} ++ (c);
\draw[->] (c) -- (b);
```

In a case like this, we can just forget about `q` entirely, since `a(q)` carries
the same information. I call it antiquing because it's like making `q` look
older than it really is.

One great thing about the "sets of patches" thing above is that it let us
easily generalize antiquing from pairs of patches to arbitrarily complicated
histories. I'll skip the details, but the idea is that you keep antiquing
a patch -- moving it back and back in the history -- until you can't any more.
The fact that perfect merges are associative implies, as it turns out,
that every patch has a unique "most antique" version. The set of patches
leading into the most antique version of `q` are called `q`'s *dependencies*.
For example, here is a pair of patches where the second one cannot be
antiqued (as an exercise, try to explain why not):

```tikz
FILE (0, 0)
to-do list:

FILE (50, 0)
to-do list:
* put on shoes

FILE (100, 0)
to-do list:
* put on shoes
* go to work

EDGES
a1 b1
b1 c1
b2 c2
```

Since the second patch can't be made any more antique, the first patch above is
a dependency of the second one. In my next post, I'll come back to antiquing
(and specifically, the question of how to efficiently find the most
antique version of a patch).

I promised to talk about reordering patches, so why did I spend paragraphs
going on about antiques? The point is that (again, because of the associative
property of perfect merges) patches in "parallel" can be applied in any order.
The point of antiquing is to make patches as parallel as possible, and so
then we can be maximally flexible about ordering them.

That last bit is important, so it's worth saying again (and with a picture):
patches in sequence

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (2, 0) {\tt A};
\node (b) at (4, 0) {\tt B};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (a) -- node[above] {\tt q} ++ (b);
```

cannot be re-ordered; the same information represented in parallel using an
antique of `q`

```tikz
EXTRA
\node (o) at (0, 0) {\tt O};
\node (a) at (3, 2) {\tt A};
\node (c) at (3, -2) {\tt C};
\draw[->] (o) -- node[above] {\tt p} ++ (a);
\draw[->] (o) -- node[above] {\tt a(q)} ++ (c);
```

is much more flexible.

## Case study 2: parallel development

Since I've gone on for so long about reordering patches, let's have an example
showing what it's good for. Let me start with some good news: you don't need
to know about antiquing to use pijul, because pijul does it all for you:
whenever pijul records a patch, it automatically records the most antique
version of that patch. All you'll notice is the extra flexibility it brings.

We'll simulate (a toy example of) a common scenario: you're maintaining a
long-running branch of a project that's under active development (maybe you're
working on a large experimental feature). Occasionally, you need to
exchange some changes with the master branch. Finally (maybe your experimental feature
was a huge success) you want to merge everything back into master.

Specifically, we're going to do the following experiment in both pijul and git.
The master branch will evolve in the following sequence:

```tikz
FILE (0, 0)
to-do list:
* put on shoes

FILE (50, 0)
to-do list:
* put on shoes
* go outside

FILE (100, 0)
to-do list:
* URGENT FIX
* put on shoes
* go outside

FILE (150, 0)
to-do list:
* put on socks
* URGENT FIX
* put on shoes
* go outside

EDGES
a1 b1
a2 b2
b1 c1
b2 c3
b3 c4
c1 d1
c2 d3
c3 d4
c4 d5
```

On our private branch, we'll begin from the same initial file.
We'll start by applying the urgent fix from the master branch
(it fixed a critical bug, so we can't wait):

```tikz
FILE (0, 0)
to-do list:
* URGENT FIX
* put on shoes
```

Then we'll get to implementing our fancy experimental features:

```tikz
FILE (0, 0)
to-do list:
* URGENT FIX
* do the dishes
* sweep the floor
* put on shoes
```

I'll leave out the (long) command listings needed to implement the steps
above in pijul and git, but let me mention the one step that we
didn't cover before: in order to apply the urgent fix from master, we say

```
$ pijul changes --branch master # Look for the patch you want
$ pijul apply <hash-of-the-patch>
```

In git, of course, we'll use cherry-pick.

Now for the results. In pijul, merging our branch with the master branch
gives no surprises:

```tikz
FILE (0, 0)
to-do list:
* put on socks
* URGENT FIX
* do the dishes
* sweep the floor
* put on shoes
* go outside
```

In git, we get a conflict:

```tikz
FILE (0, 0)
to-do list:
<<<<<<< HEAD
* URGENT FIX
* do the dishes
* sweep the floor
=======
* put on socks
* URGENT FIX
>>>>>>> master
* put on shoes
* go outside
```

There's something else a bit funny with git's behavior here: if we resolve the
conflict and look at the
history, there are two copies of the urgent fix, with two different hashes.
Since git doesn't understand patch reordering like pijul does, `git
cherry-pick` and `pijul apply` work in slightly different ways: `pijul apply`
just adds another patch into your set of patches, while `git cherry-pick`
actually creates a new patch that looks a bit like the original. From then on,
git sees the original patch and its cherry-picked one as two different patches,
which (as we've seen) creates problems from merging down the line.
And it gets worse: reverting one of the copies of the urgent fix (try it!) gives
pretty strange results.

By playing around with this example, you can get git to do some
slightly surprising things. (For example, by inserting an extra merge in
the right place, you can get the conflict to go away. That's because git
has a heuristic where if it sees two different patches doing the same
thing, it suppresses the conflict.)

Pijul, on the other hand, understood that the urgent fix could be incorporated
into my private branch with no lossy modifications. That's
because pijul silently antiqued the urgent fix, so that
the divergence between the master branch and my own branch became irrelevant.

# Conclusion

So hopefully you have some idea now of what pijul can and can't do for you.
It's an actively developed implementation of an exciting (for me, at least) new
way of looking at patches and merges, and it has a simple, fast, and totally
lossless merge algorithm with nice properties.

Will it dethrone git? Certainly not yet. For a start, it's still
alpha-quality and under heavy development; not only should you be
worried about your data, it has several UI warts as well. Looking toward
the future, I can see reasonable arguments in both directions.

Arguing against pijul's future world domination, you could question the
relevance of the examples I've shown. How often do you really end up tripping
on git's little corner cases? Would the time saved from pijul's improvements
actually justify the cost of switching? Those are totally reasonable
questions, and I don't know the answer.

But here's a more optimistic point of view: pijul's effortless merging
and reordering might really lead to new and productive workflows. Are you
old enough to remember when git was new and most people were still on SVN
(or even CVS)? Lots of people were (quite reasonably) skeptical. "Who
cares about easy branching? It's better to merge changes immediately anyway."
Or, "who cares about distributed repositories? We have a central server,
so we may as well use it." Those arguments sound silly now that we're
all used to DVCSes and the workflow improvements that they bring, but
it took time and experimentation to develop those workflows, and the gains
weren't always obvious beforehand. Could the same progression happen with
pijul?

In the next post, I'll take a look at pijul's innards, focussing particularly on
how it represents your precious data.

# Acknowledgement

I'd like to thank Pierre-Étienne Meunier for his comments and corrections on
a draft of this post. Of course, any errors that remain are my own
responsibility.
