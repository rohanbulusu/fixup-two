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
    """'Safe' and reusable weak references to instance methods"""

    # repository of all instantiated BoundMethodWeakrefs
    _all_instances = weakref.WeakValueDictionary()

    def __new__(cls, target, on_delete=None):
        """interrupts normal object creation process to add the instance to _all_instances"""

        instance_hash = cls.get_instance_key(target)

        # if 'target' is already in _all_instances, add the 'on_delete' cleanup if specified
        if instance_hash in cls._all_instances:
            existing_obj = cls._all_instances[instance_hash]
            if on_delete:
                existing_obj.cleanup_methods.append(on_delete)
            return cls._all_instances[instance_hash]

        obj = super().__new__(cls)
        cls._all_instances[instance_hash] = obj
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
        self.cleanup_methods = [on_delete] if on_delete else []
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

        # run all the cleanup methods in self.cleanup_methods
        for cleanup_method in self.cleanup_methods:
            cleanup_method(self)

        # remove all references to the BoundMethodWeakref's cleanup methods
        del self.cleanup_methods

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
        """Returns a strong reference (specifically, a bound instance method)
           for our object and function

        NOTE:
        This method may be called any number of times, as it does
        not invalidate the reference
        """

        target = self.weak_self()
        function = self.weak_func()
        return function.__get__(target)
