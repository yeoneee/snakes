"""Backport of Python 2.6 'ast' module.

AST classes are wrappers around classes in Python 2.5 '_ast' module.
The rest is copied from Python 2.6 'ast.py'.
"""

import inspect
import _ast
from _ast import PyCF_ONLY_AST
from _ast import AST

for name, cls in inspect.getmembers(_ast, inspect.isclass) :
    if issubclass(cls, AST) :
        if cls is AST :
            continue
        class _Ast (cls, AST) :
            def __init__ (self, *larg, **karg) :
                if len(larg) > 0 and len(larg) != len(self._fields) :
                    raise TypeError, ("%s constructor takes either 0 or "
                                      "%u positional arguments"
                                      % (self.__class__.__name__,
                                         len(self._fields)))
                for name, arg in zip(self._fields, larg) + karg.items() :
                    if name in self._fields :
                        setattr(self, name, arg)
                    else :
                        getattr(self, name)
        try :
            _Ast._fields = tuple(cls._fields)
        except :
            _Ast._fields = ()
        _Ast.__name__ = name
        globals()[name] = _Ast

del _Ast, cls, name

def literal_eval(node_or_string):
    """
    Safely evaluate an expression node or a string containing a Python
    expression.  The string or node provided may only consist of the following
    Python literal structures: strings, numbers, tuples, lists, dicts, booleans,
    and None.
    """
    _safe_names = {'None': None, 'True': True, 'False': False}
    if isinstance(node_or_string, basestring):
        node_or_string = parse(node_or_string, mode='eval')
    if isinstance(node_or_string, Expression):
        node_or_string = node_or_string.body
    def _convert(node):
        if isinstance(node, Str):
            return node.s
        elif isinstance(node, Num):
            return node.n
        elif isinstance(node, Tuple):
            return tuple(map(_convert, node.elts))
        elif isinstance(node, List):
            return list(map(_convert, node.elts))
        elif isinstance(node, Dict):
            return dict((_convert(k), _convert(v)) for k, v
                        in zip(node.keys, node.values))
        elif isinstance(node, Name):
            if node.id in _safe_names:
                return _safe_names[node.id]
        raise ValueError('malformed string')
    return _convert(node_or_string)

def dump(node, annotate_fields=True, include_attributes=False):
    """
    Return a formatted dump of the tree in *node*.  This is mainly useful for
    debugging purposes.  The returned string will show the names and the values
    for fields.  This makes the code impossible to evaluate, so if evaluation is
    wanted *annotate_fields* must be set to False.  Attributes such as line
    numbers and column offsets are not dumped by default.  If this is wanted,
    *include_attributes* can be set to True.
    """
    def _format(node):
        if isinstance(node, AST):
            fields = [(a, _format(b)) for a, b in iter_fields(node)]
            rv = '%s(%s' % (node.__class__.__name__, ', '.join(
                ('%s=%s' % field for field in fields)
                if annotate_fields else
                (b for a, b in fields)
            ))
            if include_attributes and node._attributes:
                rv += fields and ', ' or ' '
                rv += ', '.join('%s=%s' % (a, _format(getattr(node, a)))
                                for a in node._attributes)
            return rv + ')'
        elif isinstance(node, list):
            return '[%s]' % ', '.join(_format(x) for x in node)
        return repr(node)
    if not isinstance(node, AST):
        raise TypeError('expected AST, got %r' % node.__class__.__name__)
    return _format(node)

def copy_location(new_node, old_node):
    """
    Copy source location (`lineno` and `col_offset` attributes) from
    *old_node* to *new_node* if possible, and return *new_node*.
    """
    for attr in 'lineno', 'col_offset':
        if attr in old_node._attributes and attr in new_node._attributes \
           and hasattr(old_node, attr):
            setattr(new_node, attr, getattr(old_node, attr))
    return new_node

def fix_missing_locations(node):
    """
    When you compile a node tree with compile(), the compiler expects lineno and
    col_offset attributes for every node that supports them.  This is rather
    tedious to fill in for generated nodes, so this helper adds these attributes
    recursively where not already set, by setting them to the values of the
    parent node.  It works recursively starting at *node*.
    """
    def _fix(node, lineno, col_offset):
        if 'lineno' in node._attributes:
            if not hasattr(node, 'lineno'):
                node.lineno = lineno
            else:
                lineno = node.lineno
        if 'col_offset' in node._attributes:
            if not hasattr(node, 'col_offset'):
                node.col_offset = col_offset
            else:
                col_offset = node.col_offset
        for child in iter_child_nodes(node):
            _fix(child, lineno, col_offset)
    _fix(node, 1, 0)
    return node

def increment_lineno(node, n=1):
    """
    Increment the line number of each node in the tree starting at *node* by *n*.
    This is useful to "move code" to a different location in a file.
    """
    if 'lineno' in node._attributes:
        node.lineno = getattr(node, 'lineno', 0) + n
    for child in walk(node):
        if 'lineno' in child._attributes:
            child.lineno = getattr(child, 'lineno', 0) + n
    return node

def iter_fields(node):
    """
    Yield a tuple of ``(fieldname, value)`` for each field in ``node._fields``
    that is present on *node*.
    """
    for field in node._fields:
        try:
            yield field, getattr(node, field)
        except AttributeError:
            pass

def iter_child_nodes(node):
    """
    Yield all direct child nodes of *node*, that is, all fields that are nodes
    and all items of fields that are lists of nodes.
    """
    for name, field in iter_fields(node):
        if isinstance(field, AST):
            yield field
        elif isinstance(field, list):
            for item in field:
                if isinstance(item, AST):
                    yield item

def get_docstring(node, clean=True):
    """
    Return the docstring for the given node or None if no docstring can
    be found.  If the node provided does not have docstrings a TypeError
    will be raised.
    """
    if not isinstance(node, (FunctionDef, ClassDef, Module)):
        raise TypeError("%r can't have docstrings" % node.__class__.__name__)
    if node.body and isinstance(node.body[0], Expr) and \
       isinstance(node.body[0].value, Str):
        if clean:
            return inspect.cleandoc(node.body[0].value.s)
        return node.body[0].value.s

def walk(node):
    """
    Recursively yield all child nodes of *node*, in no specified order.  This is
    useful if you only want to modify nodes in place and don't care about the
    context.
    """
    from collections import deque
    todo = deque([node])
    while todo:
        node = todo.popleft()
        todo.extend(iter_child_nodes(node))
        yield node

class NodeVisitor(object):
    """
    A node visitor base class that walks the abstract syntax tree and calls a
    visitor function for every node found.  This function may return a value
    which is forwarded by the `visit` method.

    This class is meant to be subclassed, with the subclass adding visitor
    methods.

    Per default the visitor functions for the nodes are ``'visit_'`` +
    class name of the node.  So a `TryFinally` node visit function would
    be `visit_TryFinally`.  This behavior can be changed by overriding
    the `visit` method.  If no visitor function exists for a node
    (return value `None`) the `generic_visit` visitor is used instead.

    Don't use the `NodeVisitor` if you want to apply changes to nodes during
    traversing.  For this a special visitor exists (`NodeTransformer`) that
    allows modifications.
    """
    def visit(self, node):
        """Visit a node."""
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)
    def generic_visit(self, node):
        """Called if no explicit visitor function exists for a node."""
        for field, value in iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, AST):
                        self.visit(item)
            elif isinstance(value, AST):
                self.visit(value)

class NodeTransformer(NodeVisitor):
    """
    A :class:`NodeVisitor` subclass that walks the abstract syntax tree and
    allows modification of nodes.

    The `NodeTransformer` will walk the AST and use the return value of the
    visitor methods to replace or remove the old node.  If the return value of
    the visitor method is ``None``, the node will be removed from its location,
    otherwise it is replaced with the return value.  The return value may be the
    original node in which case no replacement takes place.

    Here is an example transformer that rewrites all occurrences of name lookups
    (``foo``) to ``data['foo']``::

       class RewriteName(NodeTransformer):

           def visit_Name(self, node):
               return copy_location(Subscript(
                   value=Name(id='data', ctx=Load()),
                   slice=Index(value=Str(s=node.id)),
                   ctx=node.ctx
               ), node)

    Keep in mind that if the node you're operating on has child nodes you must
    either transform the child nodes yourself or call the :meth:`generic_visit`
    method for the node first.

    For nodes that were part of a collection of statements (that applies to all
    statement nodes), the visitor may also return a list of nodes rather than
    just a single node.

    Usually you use the transformer like this::

       node = YourTransformer().visit(node)
    """
    def generic_visit(self, node):
        for field, old_value in iter_fields(node):
            old_value = getattr(node, field, None)
            if isinstance(old_value, list):
                new_values = []
                for value in old_value:
                    if isinstance(value, AST):
                        value = self.visit(value)
                        if value is None:
                            continue
                        elif not isinstance(value, AST):
                            new_values.extend(value)
                            continue
                    new_values.append(value)
                old_value[:] = new_values
            elif isinstance(old_value, AST):
                new_node = self.visit(old_value)
                if new_node is None:
                    delattr(node, field)
                else:
                    setattr(node, field, new_node)
        return node

def _ast2ast (node) :
    new = globals()[node.__class__.__name__]()
    if not hasattr(node, "_fields") or node._fields is None :
        node._fields = ()
    for name, field in iter_fields(node) :
        new_field = field
        if field is None :
            new_field = None
        elif isinstance(field, AST) :
            new_field = _ast2ast(field)
        elif isinstance(field, list) :
            new_field = []
            for value in field :
                if isinstance(value, AST) :
                    new_field.append(_ast2ast(value))
                else :
                    new_field.append(value)
        setattr(new, name, new_field)
    copy_location(new, node)
    return new

def parse(expr, filename='<unknown>', mode='exec'):
    """
    Parse an expression into an AST node.
    Equivalent to compile(expr, filename, mode, PyCF_ONLY_AST).
    """
    return _ast2ast(compile(expr, filename, mode, PyCF_ONLY_AST))
