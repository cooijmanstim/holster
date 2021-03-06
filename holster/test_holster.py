from __future__ import absolute_import
import unittest
import holster.holster as holster
from holster import H

class HolsterTest(unittest.TestCase):
  def test(self):
    h = H([("c.d", H(e=3)), ("c.f.g", 4), ("c.f.h", [5])], a=1, b=2)
    self.assertEqual(h.a, 1)
    self.assertEqual(h.b, 2)
    self.assertEqual(h.c.d.e, 3)
    self.assertEqual(h.c.f.g, 4)
    self.assertEqual(h.c.f.h, [5])
    g = h.Narrow("c.d.e c.f.h")
    with self.assertRaises(KeyError): g.a
    with self.assertRaises(KeyError): g.c.f.g
    self.assertEqual(g.c.d.e, 3)
    self.assertEqual(g.c.f.h, [5])
    g = h.c.f
    self.assertEqual(dict(g.Items()),
                     dict(g=4, h=[5]))
    self.assertEqual(set(h.Keys()), set("c.d.e c.f.g c.f.h a b".split()))
    self.assertEqual(h.FlatCall(lambda x: x), h)
    self.assertEqual(h.c.FlatCall(lambda x: x), h.c)

  def test_subalternatives(self):
    self.assertEqual(holster.subalternatives("a", "a.b a.c.e a.c.d d.a"), "b c.e c.d")
    with self.assertRaises(KeyError): holster.subalternatives("a.e", "a.b a.c.e a.c.d d.a")
    self.assertEqual(holster.subalternatives("a.b", "a.b a.c.e a.c.d d.a"), "")

  def test_regression1(self):
    h = H()
    h["g.t"] = 0
    h.g.v = 1
    self.assertEqual(set(h.g.Keys()), set("tv"))
    self.assertEqual(set(h.g.Narrow("t v").Keys()), set("tv"))

  def test_regression2(self):
    h = H(k=H())
    h.k.l = 2
    g = H()
    h = H(k=H())
    g.h = h
    g.h.k.l = 2
    i = h.Map(lambda x: x + 1)
    self.assertEqual(i.Size(), 0)
    i.k.l = 2

if __name__ == "__main__":
  unittest.main()
