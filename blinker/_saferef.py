# extracted from Louie, http://pylouie.org/
# updated for Python 3
#
# Copyright (c) 2006 Patrick K. O'Brien, Mike C. Fletcher,
#                    Matthew R. Scott
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#
#     * Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#
#     * Neither the name of the <ORGANIZATION> nor the names of its
#       contributors may be used to endorse or promote products derived
#       from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

import sys
import traceback
import weakref


def safe_ref(target, on_delete=None):
    """wraps a *safe* reference in a weakref
    target: the object to be wrapped in a weak reference
    on_delete: if provided, stores a hard reference to 'target' which will be
               called after the safe reference goes out of scope
    """

    # if 'target' is a bound method, wrap it in a BoundMethodWeakref
    if hasattr(target, '__self__'):
        if not hasattr(target, '__func__'):
            raise TypeError(f'Target {target} is bound but not a method')
        return BoundMethodWeakref(target, on_delete)

    # if on_delete was specified, pass it to weakref.ref too
    if on_delete:
        if not callable(on_delete):
            raise TypeError("Keyword argument 'on_delete' must be callable")
        return weakref.ref(target, on_delete)

    return weakref.ref(target)


class BoundMethodWeakref:
    """'Safe' and reusable weak references to instance methods.

    BoundMethodWeakref objects provide a mechanism for referencing a
    bound method without requiring that the method object itself
    (which is normally a transient object) is kept alive.  Instead,
    the BoundMethodWeakref object keeps weak references to both the
    object and the function which together define the instance method.

    Attributes:

    - ``key``: The identity key for the reference, calculated by the
      class's get_instance_key method applied to the target instance method.

    - ``deletion_methods``: Sequence of callable objects taking single
      argument, a reference to this object which will be called when
      *either* the target object or target function is garbage
      collected (i.e. when this object becomes invalid).  These are
      specified as the on_delete parameters of safe_ref calls.

    - ``weak_self``: Weak reference to the target object.

    - ``weak_func``: Weak reference to the target function.

    Class Attributes:

    - ``_all_instances``: Class attribute pointing to all live
      BoundMethodWeakref objects indexed by the class's
      get_instance_key(target) method applied to the target objects.
      This weak value dictionary is used to short-circuit creation so
      that multiple references to the same (object, function) pair
      produce the same BoundMethodWeakref instance.
    """

    _all_instances = weakref.WeakValueDictionary()

    def __new__(cls, target, on_delete=None, *arguments, **named):
        """interrupts normal object creation process to add the instance to _all_instances"""

        instance_key = cls.get_instance_key(target)

        # if 'target' is already in _all_instances for whatever reason
        if instance_key in cls._all_instances:
            current = cls._all_instances.get(instance_key)
            current.deletion_methods.append(on_delete)
            return current

        obj = super().__new__(cls)
        cls._all_instances[instance_key] = obj
        return obj

    def __init__(self, target, on_delete=None):
        """returns a weak-reference-like instance for a bound method.

        - ``target``: the target for the weak reference,
          must have im_self and im_func attributes and be
          reconstructable by: target.im_func.__get__(target.im_self)

        - ``on_delete``: optional callback which will be called when
          this weak reference ceases to be valid (i.e. either the
          object or the function is garbage collected); should take a single
          argument
        """
        self.deletion_methods = [on_delete] if on_delete else []
        self.key = self.get_instance_key(target)

        self.weak_self = weakref.ref(target.__self__, self._remove)
        self.weak_func = weakref.ref(target.__func__, self._remove)

        self.self_name = str(target.__self__)
        self.func_name = str(target.__func__)

    def _remove(self, weak):
        """delete all references to both the object's owner (__self__)
           and the method instance (__func__)"""

        # remove the instance from BoundMethodWeakref._all_instances
        del self.__class__._all_instances[self.key]

        # run all the cleanup methods in self.deletion_methods
        for cleanup_method in self.deletion_methods:
            cleanup_method(self)

        # remove all references to the BoundMethodWeakref's cleanup methods
        del self.deletion_methods

    @staticmethod
    def get_instance_key(target):
        """calculates the reference key for the given target"""
        return hash((id(target.__self__), id(target.__func__)))

    def __repr__(self):
        return f'{self.__class__.__name__}({self.self_name}.{self.func_name})'

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            return cmp(self.__class__, type(other))
        return cmp(self.key, other.key)

    def __call__(self):
        """Return a strong reference to the bound method.

        If the target cannot be retrieved, then will return None,
        otherwise returns a bound instance method for our object and
        function.

        Note: You may call this method any number of times, as it does
        not invalidate the reference.
        """
        target = self.weak_self()

        function = self.weak_func()
        if function is not None:
            return function.__get__(target)
