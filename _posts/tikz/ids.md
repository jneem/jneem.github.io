---
layout: post
title: "Part 4: Line IDs"
---

I've written quite a bit about the *theory* of patches and merging, but nothing
yet about how to actually implement anything efficiently. That will be the
subject of this post, and probably some future posts too.  Algorithms and
efficiency are not really discussed in the original
[paper](https://arxiv.org/abs/1311.3903), so most of this material I learned
from reading the [pijul](https://pijul.com) source code. Having said that,
my main focus here is on broader ideas and algorithms, and so you shouldn't
assume that anything written here is an accurate reflection of pijul
(plus, my pijul knowledge is about 2 years out of date by now).

# Three sizes

Before getting to the juicy details, we have to decide what it means for things
to be fast. In a VCS, there are three different size scales that we need
to think about. From smallest to biggest, we have:

1. The size of the *change*. Like, if we're changing one line in a giant file,
   then the size of the change is just the length of the one line that we're
   changing.
2. The size of the *current output*. In the case of ojo (which just tracks
   a single file), this is just the size of the file.
3. The size of the *history*. This includes everything that has ever been in
   the repository, so if the repository has been active for years then the size
   of the history could be much bigger than the current size.

The first obvious requirement is that the size of a patch should be
proportional to the size of the change. This sounds almost too obvious to
mention, but remember the definition of a patch from
[here]({{ site.baseurl }}{% post_url 2017-05-08-merging %}#graggles): a
patch consists of a source file, a target file, and a function from one to the
other that has certain additional properties. If we were to naively translate
this definition into code, the size of a patch would be proportional to the
size of the entire file.

Of course, this is a solved problem in the world of UNIX-style diffs (which I
mentioned all the way back in the
[first post]({{ site.baseurl }}{% post_url 2017-05-08-merging %})).
The problem is to adapt the diff approach to our mathematical patch framework;
for example, the fact that our files need not even be ordered means that it
doesn't make sense to talk about inserting a line "after line 62."

The key to solving this turns out to be to unique IDs: give every line in the
entire history of the repository a unique ID. This isn't even very difficult:
we can give every patch in the history of the repository a unique ID by hashing
its contents. For each patch, we can enumerate the lines that it adds and then
for the rest of time, we can uniquely refer to those lines like "the third line
added by patch `Ar8f`."

# Representing patches

Once we've added unique IDs to every line, it becomes pretty easy to encode
patches compactly. For example, suppose we want to describe this patch:

```tikz
DAGLE (0, 0)
PARENT 0 POS 1/1 dA/0:to-do
PARENT 1 POS 2/1 dA/1:shoes
PARENT 2 POS 3/1 dA/2:garbage

DAGLE (50, 0)
PARENT 0 POS 1/1 dA/0:to-do
PARENT 1 POS 2/1 GHOSTdA/1: shoes
PARENT 2 POS 3/1 dA/2:garbage
PARENT 3 POS 4/1 x5/0:work

EDGES
a1 b1
a2 b2 dashed
a3 b3
```

Here, `dA` is the unique ID of the patch that introduced the to-do, shoes, and
garbage lines, and `x5` is the unique ID of the patch that we want to describe.
Anyway, the patch is now easy to describe by using the unique IDs to specify
what we want to do: delete the line with ID `dA/1`, add the line with ID `x5/0`
and contents "work", and add an edge from the line `dA/2` to the line
`x5/0`.

Let's have a quick look at how this is implemented in ojo, by taking a peek
at the [API docs](https://docs.rs/libojo/0.1.0/libojo/).  Patches, funnily
enough, are represented by the
[`Patch`](https://docs.rs/libojo/0.1.0/libojo/struct.Patch.html) struct, which
basically consists of metadata (author, commit message, timestamp) and a list
of [`Change`](https://docs.rs/libojo/0.1.0/libojo/enum.Change.html)s. The
`Change`s are the most interesting part, and they look like this:

```rust
pub enum Change {
    NewNode { id: NodeId, contents: Vec<u8> },
    DeleteNode { id: NodeId },
    NewEdge { src: NodeId, dest: NodeId },
}
```

In other words, the example that we saw above is basically all there is to it,
as far as patches go.

If you want to see what actual patches look like in actual usage, you can do
that too because ojo keeps all of its data in human-readable text. After installing
ojo (with `cargo install ojo`), you can create a new repository (with `ojo
init`), edit the file `ojo_file.txt` with your favorite editor, and then:

```console
$ ojo patch create -m "Initial commit" -a Me
Created patch PMyANESmvMQ8WR8ccSKpnH8pLc-uyt0jzGkauJBWeqx4=
$ ojo patch export -o out.txt PSc97nCk9oRrRl-2IW3H8TYVtA0hArdVtj5F0f4YSqqs=
Successfully wrote the file 'out.txt'
```

Now look in `out.txt` to see your `NewNode`s and `NewEdge`s in all their glory.

# Antiquing

I introduced unique IDs as a way to achieve compact representations of patches,
but it turns out that they also solve a problem that I promised to explain
[two years ago]({{ site.baseurl }}{% post_url 2017-05-13-pijul %}):
how do I compute the "most antique"
version of a patch? Or equivalently, if I have some patch but I want to apply
it to a slightly different repository, how do I know whether I can do that?
With our description of patches above, this is completely trivial: a patch can
only add lines, delete lines, or add edges. Adding lines is always valid, no
matter what the repository contains. Deleting lines and adding edges can be
done if and only if the lines to delete, or the lines to connect, exist in the
repository. Since lines have unique IDs, checking this is unambiguous.
Actually, it's really easy because the line IDs are tied to the patch that
introduced them: a patch can be applied if and only if all the patch IDs that
it refers to have already been applied. For obvious reasons, we refer to these
as "dependencies": the dependencies of a patch are all the other patches that
it refers to in `DeleteNode` and `NewEdge` commands. You can see this in action
[here](https://github.com/jneem/ojo/blob/c0eac6d5248e6ef4f811b72819794786b54f09a4/libojo/src/patch.rs#L203).

By the way, this method will always give a minimal set of dependencies (in
other words, the most antique version of a patch), but it isn't necessarily
the right thing to do. For example, if a patch deletes a line then it seems
reasonable for it to also depend on the lines *adjacent* to the deleted line.
Ojo might do this in the future, but for now it sticks to the minimal
dependencies.

# Applying patches

Now that we know how to compactly represent patches, how quickly can we apply
them?  To get really into detail here, we'd need to talk about how the state of
the repository is represented on disk (which is an interesting topic on its
own, but a bit out of scope for this post). Let's just pretend for now that the
current state of the repository is stored as a graph in memory, using some
general-purpose crate
(like, say, [`petgraph`](https://docs.rs/petgraph/0.4.13/petgraph/)).
Each node in the graph needs to store the contents of the corresponding line,
as well as a "tombstone" saying whether it has been deleted
(see [the first post](https://jneem.github.io/merging/)). Assuming we can
add nodes and edges in constant time (like, say, in `petgraph`), applying
a single change is a constant time operation. That means the time it takes
to apply the whole patch is proportional to the number of changes.
That's the best we could hope for, so we're done, right? What was even the
point of the part about three size scales?

# Revenge of the ghosts

Imagine you have a file that contains three lines:

```text
first line
second line
last line
```

but behind the scenes, there are a bunch of lines that used to be there. So
ojo's representation of your file might look like:

```tikz
DAGLE (0, 0)
PARENT 0 POS 1/1 first line
PARENT 1 POS 2/1 GHOST sceond line
PARENT 2 POS 3/1 GHOST oops
PARENT 3 POS 4/1 GHOST second lnie
PARENT 4 POS 5/1 GHOST aargh
PARENT 5 POS 6/1 GHOST secondl ine
PARENT 6 POS 7/1 GHOST ok
PARENT 7 POS 8/1 GHOST calm down
PARENT 8 POS 9/1 second line
PARENT 9 POS 10/1 last line
```

Now let's imagine that we delete "second line." The patch to do this consists
of a single `DeleteLine` command, and it takes almost no time to apply:

```tikz
DAGLE (0, 0)
PARENT 0 POS 1/1 first line
PARENT 1 POS 2/1 GHOST sceond line
PARENT 2 POS 3/1 GHOST oops
PARENT 3 POS 4/1 GHOST second lnie
PARENT 4 POS 5/1 GHOST aargh
PARENT 5 POS 6/1 GHOST secondl ine
PARENT 6 POS 7/1 GHOST ok
PARENT 7 POS 8/1 GHOST calm down
PARENT 8 POS 9/1 GHOST second line
PARENT 9 POS 10/1 last line
```

Now that we have this internal representation, ojo needs to create a file
on disk showing the new state. That is, we want to somehow go from the internal
representation above to the file

```text
first line
last line
```

Do you see the problem? Even though the output file is only two lines long, in
order to produce it we need to visit all of the lines that used to be there but
have since been deleted. In other words, we can apply patches quickly (in
timescale 1), but rendering the output file is slow (in timescale 3). For a
real VCS that tracks decade-old repositories, that clearly isn't going to fly.

# Pseudo-edges

There are several ingredients that go into supporting fast rendering of output
files (fast here means "timescale 2, most of the time", which is the best that
we can hope for). Those are going to be the subject of the next post. So that
you have something to think about until then, let me get you started: the key
idea is to introduce "pseudo-edges," which are edges that we insert on our own
in order to allow us to "skip" large regions of deleted lines. In the example
above, the goal is to actually generate this graph:

```tikz
DAGLE (0, 0)
PARENT 0 POS 1/1 first line
PARENT 1 POS 2/1 GHOST sceond line
PARENT 2 POS 3/1 GHOST oops
PARENT 3 POS 4/1 GHOST second lnie
PARENT 4 POS 5/1 GHOST aargh
PARENT 5 POS 6/1 GHOST secondl ine
PARENT 6 POS 7/1 GHOST ok
PARENT 7 POS 8/1 GHOST calm down
PARENT 8 POS 9/1 GHOST second line
PARENT 9 POS 10/1 last line

EXTRA
\draw[->, thick, dotted] (a1.east) to [out=0,in=0] (a10.east);
```

These extra edges will allow us to quickly render output files, but they open
up a new can of worms (and were the source of several subtle bugs in `pijul`
last time I used it (i.e. two years ago)): how do we know when to add (or
remove, or update) pseudo-edges? Keep in mind that we aren't willing to
traverse the entire graph to compute the pseudo-edges, because that would
defeat the purpose.
