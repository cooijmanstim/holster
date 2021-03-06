"""Holster is a dict-like data structure that exposes its items as attributes, and provides easy
access to objects deep into nested structures with a minimum of syntactic noise. See the tests for
examples.

To avoid name clashes, keys are restricted to be lower-case, leaving upper-case for methods.

Where it makes sense, methods that take a key can take it in the following forms:
  - a simple key representing a single attr lookup: "attr1"
  - a composition of simple keys: "attr1.attr2.attr3"
  - a disjunction of space-separated alternatives: "attr1 attr2.attr3"
"""
from __future__ import absolute_import
import contextlib
from collections import OrderedDict as ordict
import itertools as it, functools as ft
import holster.util as util

# NOTE: disjunctions grow quadratically
def composekey(*keys):
  """Compose a sequence of keys into one key.

  Example: composekey("attr1.attr2", "attr3") == "attr1.attr2.attr3"
  """
  keys = [key.split() for key in keys]
  composites = [[]]
  for alternatives in keys:
    composites = [com + [alt] for alt in alternatives for com in composites]
  return " ".join(".".join(key) for key in composites)

def uncomposekey(prefix, key):
  """Remove a prefix from a composite key.

  Example: uncomposekey("attr1.attr2", "attr1.attr2.attr3.attr4") == "attr3.attr4"
  """
  if " " in prefix or " " in key:
    raise NotImplementedError()
  prefix, key = prefix.split("."), key.split(".")
  while prefix:
    a, b = prefix.pop(0), key.pop(0)
    if a != b:
      raise ValueError("key %s does not have prefix %s" % (key, prefix))
  return ".".join(key)

def insubforest(subkey, key):
  """Test whether `subkey` has one of alternatives in `key` as prefix."""
  try:
    subalts = subalternatives(subkey, key)
  except KeyError:
    return False
  return not subalts

def insubtree(subkey, key):
  """Test whether `subkey` has `key` as prefix."""
  try:
    subalt = subalternative(subkey, key)
  except KeyError:
    return False
  return not subalt

def subalternative(key, alt):
  """Determine leftover of constraint `alt` after selecting `key`.

  Mainly used in Narrow, where a key may select a subtree of the non-narrowed Holster and needs
  further narrowing. For example, if `h = H(a=H(b=3, c=5))` then `h.Narrow("a.b").a` should select
  the narrowed subtree `HolsterSubtree(h, "a").Narrow("b")`. In this case, `subalternative("a",
  "a.b") == "b"`, as `b` is the yet unenforced part of the narrowing constraint `a.b` after
  selecting `a`.

  Also used by `insubtree`, which requires that there is no leftover, i.e. `key` is fully underneath
  `alt`.

  :returns: If `key` is a prefix of `alt`, returns `alt` with the prefix `key` removed. If `alt` is
    a prefix of `key`, returns the empty string (meaning no constraints left to enforce).
  """
  assert " " not in key
  assert " " not in alt
  keyparts, altparts = key.split("."), alt.split(".")
  while keyparts and altparts:
    a, b = keyparts.pop(0), altparts.pop(0)
    if a != b:
      raise KeyError()
  return ".".join(altparts)

def subalternatives(key, alts):
  """Determine leftovers of constraints in `alts` after selecting `key`.

  This is like `subalternative`, but `alts` is a composite key that represents the union of multiple
  keys.

  Mainly used in Narrow, where a key may select a subtree of the non-narrowed Holster and needs
  further narrowing. For example, if `h = H(a=H(b=3, c=5))` then `h.Narrow("a.b").a` should select
  the narrowed subtree `HolsterSubtree(h, "a").Narrow("b")`. In this case, `subalternative("a",
  "a.b") == "b"`, as `b` is the yet unenforced part of the narrowing constraint `a.b` after
  selecting `a`.

  Also used by `insubforest`, which requires that there is no leftover, i.e. `key` is fully
  underneath at least one of `alts`.

  :returns: A composite key disjoining the leftover constraints.
  """
  assert " " not in key
  subalts = []
  for alt in alts.split(" "):
    try:
      subalt = subalternative(key, alt)
    except KeyError:
      continue
    subalts.append(subalt)
  if not subalts:
    raise KeyError()
  return " ".join(subalt for subalt in subalts if subalt)

def keyancestors(key, strict=False):
  """Iterate over ancestors of `key`.

  Yields all prefixes of `key`, including `key` itself if `strict` is false. `key` may be a
  composite key, in which case there is an extra outer loop over alternatives.
  """
  alternatives = key.split(" ")
  for alternative in alternatives:
    parts = alternative.split(".")
    for i in range(1, len(parts) + (0 if strict else 1)):
      yield ".".join(parts[:i])

NODEFAULT = object()

class BaseHolster(object):
  # This abstract base class defines the general Holster interface. Any behaviour it defines should
  # be in terms of the abstract interface.

  def Keys(self, _include_empty=False):
    """Iterate over keys."""
    raise NotImplementedError()

  def Get(self, key, default=NODEFAULT):
    """Obtain value associated to key `key`."""
    raise NotImplementedError()

  def Set(self, key, value):
    """Associate `key` with `value`."""
    raise NotImplementedError()

  def Delete(self, key):
    """Delete the item associated with `key`."""
    raise NotImplementedError()

  def __getattribute__(self, key):
    if key[0].isupper() or key.startswith("_"):
      return super().__getattribute__(key)
    return self.Get(key)

  def __setattr__(self, key, value):
    if key[0].isupper() or key.startswith("_"):
      super().__setattr__(key, value)
    else:
      self.Set(key, value)

  def __getitem__(self, key):
    return self.Get(key)

  def __setitem__(self, key, value):
    self.Set(key, value)

  def __delitem__(self, key):
    self.Delete(key)

  # NOTE: Holster.Keys() and Holster.__contains__() are inconsistent in the sense that keys not
  # listed by Holster.Keys() may be reported as contained in the data structure. Keys() yields leaf
  # node keys, whereas __contains__() is true for internal node keys as well.
  def __contains__(self, key):
    try:
      self.Get(key)
    except KeyError:
      return False
    else:
      return True

  def __iter__(self):
    return iter(self.Keys())

  def __eq__(self, other):
    if not isinstance(other, BaseHolster):
      return False
    if self is other:
      return True
    for key in self.Keys():
      if key not in other or self.Get(key) != other.Get(key):
        return False
    for key in other.Keys():
      if key not in self or other.Get(key) != self.Get(key):
        return False
    return True

  def __ne__(self, other):
    return not self == other

  def __bool__(self):
    return any(self.Keys())

  def __len__(self):
    return len(self.Keys())

  __nonzero__ = __bool__

  def Size(self, _include_empty=False):
    return len(list(self.Keys(_include_empty=_include_empty)))

  def Values(self):
    """Iterate over values."""
    for key in self.Keys():
      yield self.Get(key)

  def Items(self, _include_empty=False):
    """Iterate over items."""
    for key in self.Keys(_include_empty=_include_empty):
      yield (key, self.Get(key, _include_empty=_include_empty))

  def Update(self, other):
    """Update `self` with items from `other`.

    `other` can be a Holster object, a dict, or a sequence of pairs.
    """
    if isinstance(other, BaseHolster):
      for key, value in other.Items(_include_empty=True):
        self[key] = value
    elif hasattr(other, "keys"): # dict
      for key, value in other.items():
        self[key] = value
    else: # sequence of pairs
      for key, value in other:
        self[key] = value

  def Narrow(self, key):
    """Return a view narrowed to the given key.

    The returned view is a Holster object that contains only items under `key`. Being a view, it
    shares structure with `self`, and changes made to either Holster object will be reflected by
    both Holster objects.
    """
    return HolsterNarrow(self, key)
  Y = Narrow

  def FlatCall(self, fn, *args, **kwargs):
    """Call a listy function without loss of structure.

    This is useful for calling functions that take a homogeneous list and return a similar list with
    a value for each element in the original list. The simplest case of this is `map`, where `ys =
    map(f, xs)` satisfies `ys[i] = f(xs[i])`.

    This method flattens the values into a list, calls `fn`, and unflattens the resulting list into
    a new Holster object with the same keys but different values.

    `args` and `kwargs` are passed to `fn` after the list argument.

    Example:
      other = self.FlatCall(lambda xs: map(fn, xs))
      assert set(other.Keys()) == set(self.Keys())
      assert all(other[key] == fn(self[key]) for key in self.Keys())
    """
    other = Holster(util.equizip(self.Keys(), fn(list(self.Values()), *args, **kwargs)))
    other._PropagateEmpty(self)
    return other

  @classmethod
  def Map(klass, fn, *holsters):
    return klass.MapItems(lambda key, *values: (key, fn(*values)), *holsters)

  @classmethod
  def MapItems(klass, fn, *holsters):
    if not all(set(holsters[0].Keys()) == set(holster.Keys()) for holster in holsters):
      raise ValueError("cannot map over non-isomorphic holsters")
    result = Holster()
    result._PropagateEmpty(holsters[0])
    for key in holsters[0].Keys():
      values = tuple(holster[key] for holster in holsters)
      newkey, newvalue = fn(key, *values)
      result[newkey] = newvalue
    return result

  def Zip(self, other):
    """Zip values of `self` and `other` with corresponding keys.

    Returns an iterable of paired values from `self` and `other`.

    Key set and order is determined by `self`."""
    return ((self.Get(key), other.Get(key)) for key in self.Keys())

  def AsDict(self):
    """Convert to an ordered dict."""
    return ordict(self.Items())

  def With(self, items=(), **kwargs):
    """Create a copy of `self` augmented with items from `items` and `kwargs`."""
    h = Holster(self)
    h.Update(items)
    h.Update(kwargs)
    return h

  @contextlib.contextmanager
  def Bind(self, items=(), **kwargs):
    """Temporarily augment `self` with items from `items` and `kwargs`."""
    old = H()
    for key, value in it.chain(items, kwargs.items()):
      if key in self:
        old.Set(key, self[key])
      self.Set(key, value)
    yield self
    for key, value in it.chain(items, kwargs.items()):
      if key in old:
        self.Set(key, old.Get(key))
      else:
        self.Delete(key)

  def _PropagateEmpty(self, other):
    """Copy over empty namespaces from `other` into `self`."""
    for key, value in other.Items(_include_empty=True):
      if isinstance(value, EmptyHolster):
        self[key] = value

class Holster(BaseHolster):
  # The fundamental Holster object wraps an ordered dict.

  def __init__(self, items=(), **kwargs):
    self.Data = ordict()
    self.Update(items)
    self.Update(kwargs)

  def Keys(self, _include_empty=False):
    return [key for key, value in self.Data.items()
            if _include_empty or not isinstance(value, EmptyHolster)]

  def Get(self, key, default=NODEFAULT, _include_empty=False):
    assert " " not in key
    # if the key matches a leaf, return that
    if key in self.Data:
      if isinstance(self.Data[key], EmptyHolster) and not _include_empty:
        return HolsterSubtree(self, key)
      else:
        return self.Data[key]
    # else suppose key refers to a subtree
    subtree = HolsterSubtree(self, key)
    if subtree.Size(_include_empty=True) > 0:
      return subtree
    # key did not refer to an (existing) subtree
    if default is NODEFAULT:
      raise KeyError(key)
    else:
      return default

  def Set(self, key, value):
    assert " " not in key

    # key may point to a subtree of an EmptyHolster, which would violate _CheckAncestors but is a
    # specially permitted case. We delete the EmptyHolster to make room for the assignment.
    ancestors = [a for a in keyancestors(key, strict=True)
                 if a in self.Data]
    for ancestor in ancestors:
      if isinstance(self.Data[ancestor], EmptyHolster):
        del self.Data[ancestor]
      else:
        raise KeyError("cannot descend into leaf node %s at %s"
                       % (repr(self.Data[ancestor])[:50], ancestor),
                       key)

    try:
      del self[key] # to ensure descendants are gone
    except KeyError:
      pass

    if isinstance(value, BaseHolster):
      if value.Size(_include_empty=True) == 0:
        self.Data[key] = EmptyHolster()
      else:
        for k, v in value.Items(_include_empty=True):
          self.Set(composekey(key, k), v)
    else:
      self.Data[key] = value

  def Delete(self, key):
    for alt in key.split(" "):
      subtree = self.Get(alt, _include_empty=True)
      if isinstance(subtree, BaseHolster) and not isinstance(subtree, EmptyHolster):
        for subkey in list(subtree.Keys(_include_empty=True)):
          # recursive, but in the inner call subtree will be a leaf
          self.Delete(subkey)
      del self.Data[key]

  def __len__(self):
    return len([x for x in self.Data.values() if not isinstance(x, EmptyHolster)])

  def __repr__(self):
    return "Holster([%s])" % ", ".join("(%r, %r)" % (key, value)
                                       for key, value in self.Items(_include_empty=True))

  def __str__(self):
    return "H{%s}" % ", ".join("%s: %s" % (key, value)
                               for key, value in self.Items())

  def _CheckAncestors(self, key):
    # A leaf node may be present at any prefix of `key`, in which case we don't allow descending beyond it.
    #
    #   h = H(a=1)
    #   h["a.b"] = 2
    #   h.Items() => [("a", 1), ("a.b", 2)]
    #
    # This structure poses no problems for the representation, but is at odds with the conceptually
    # simple view of Holster as a nested dict.
    #
    # FIXME: it is still possible for this to be violated AFTER a HolsterSubtree is created
    ancestor = util.argany(a for a in keyancestors(key, strict=True)
                           if a in self.Data and not isinstance(self.Data[a], EmptyHolster))
    if ancestor:
      raise KeyError("cannot descend into leaf node %s at %s"
                     % (repr(self.Data[ancestor])[:50], ancestor),
                     key)

class EmptyHolster(BaseHolster):
  """Represents an empty holster.

  Nesting an empty holster inside of an outer holster is finicky because only elements are
  explicitly stored, and hence empty subtrees are treated as nonexistent. In order to mask this
  behavior, we assign an EmptyHolster instance when a user explicitly assigns an empty holster
  to be an item of an outer holster. The Holster class treats EmptyHolster as a special case
  so that its path is treated as an existing, empty subtree.
  """
  def Keys(self, _include_empty=False):
    return ()

  def Get(self, key, default=NODEFAULT, _include_empty=False):
    raise NotImplementedError()

  def Set(self, key, value):
    raise NotImplementedError()

  def Delete(self, key):
    raise NotImplementedError()

  def __len__(self):
    return 0

  def __repr__(self):
    return "EmptyHolster()"

  def __str__(self):
    return "E"

class HolsterSubtree(BaseHolster):
  """Holster object that acts as a view onto another Holster's subtree.

  Changes made on HolsterSubtree objects are reflected in the original Holster object.
  """
  def __init__(self, other, key):
    """Initialize a HolsterSubtree instance.

    :param other: underlying Holster object
    :param key: key of subtree to reflect
    """
    if " " in key:
      raise ValueError("HolsterSubtree does not support disjunctive keys")
    other._CheckAncestors(key)
    self.Other = other
    self.Key = key

  def Keys(self, _include_empty=False):
    for key in self.Other.Keys(_include_empty=_include_empty):
      if insubtree(key, self.Key):
        yield uncomposekey(self.Key, key)

  def Get(self, key, default=NODEFAULT, _include_empty=False):
    return self.Other.Get(composekey(self.Key, key), default, _include_empty=_include_empty)

  def Set(self, key, value):
    self.Other[composekey(self.Key, key)] = value

  def Delete(self, key):
    self.Other[composekey(self.Key, key)]

  def __repr__(self):
    return "HolsterSubtree(%r, %r)" % (self.Other, self.Key)

  def __str__(self):
    return "HS{%s}" % ", ".join("%s: %s" % (key, value)
                                for key, value in self.Items())

class HolsterNarrow(BaseHolster):
  """Holster object that acts as a view onto a subset of another Holster's items.

  Changes made on HolsterNarrow objects are reflected in the original Holster object.
  """
  def __init__(self, other, key):
    """Initialize a HolsterNarrow instance.

    :param other: underlying Holster object
    :param key: possibly disjunctive key to items to include
    """
    self.Other = other
    self.Key = key
    self._RequireAllKeysExist()

  def _RequireAllKeysExist(self):
    for alt in self.Key.split(" "):
      if alt not in self.Other:
        raise KeyError("narrowing to nonexistent key", alt)

  def Keys(self, _include_empty=False):
    for key in self.Other.Keys(_include_empty=_include_empty):
      if insubforest(key, self.Key):
        yield key

  def Get(self, key, default=NODEFAULT, _include_empty=False):
    assert " " not in key
    # two cases:
    # (1) key is a (nonstrict) child of one of the self.Key alternatives.
    #     In this case everything below key will match that self.Key alternative, and hence we
    #     can just return self.Other.get(key) without any further narrowing constraints.
    # (2) key selects a supertree of one of the self.Key alternatives.
    #     In this case things below key may not match the self.Key alternative, and we need to
    #     narrow the subtree returned from self.Other.get(key).
    try:
      subalts = subalternatives(key, self.Key)
    except KeyError:
      subalts = None
    if subalts is None:
      raise KeyError("key excluded by narrowing expression %s" % self.Key, key)
    result = self.Other.Get(key, default, _include_empty=_include_empty)
    if subalts and isinstance(result, HolsterSubtree):
      result = result.Narrow(subalts)
    return result

  def Set(self, key, value):
    raise NotImplementedError() # not sure what to do until I need it
    assert " " not in key
    try:
      subalts = subalternatives(key, self.Key)
    except KeyError:
      subalts = None
    # for write operations, key must be a (nonstrict) child of one of the self.Key alternatives.
    if subalts or subalts is None:
      raise KeyError("cannot write outside Narrow expression %s" % self.Key, key)
    self.Other.Set(key, value)

  def Delete(self, key):
    raise NotImplementedError() # not sure what to do until I need it
    assert " " not in key
    try:
      subalts = subalternatives(key, self.Key)
    except KeyError:
      subalts = None
    # for write operations, key must be a (nonstrict) child of one of the self.Key alternatives.
    if subalts or subalts is None:
      raise KeyError("cannot write outside Narrow expression %s" % self.Key, key)
    self.Other.Delete(key)

  def __repr__(self):
    return "HolsterNarrow(%r, %r)" % (self.Other, self.Key)

  def __str__(self):
    return "HN{%s}" % ", ".join("%s: %s" % (key, value)
                                for key, value in self.Items())

  def Narrow(self, key):
    return HolsterNarrow(self.Other, key)
