""" CSeq function inlining module
     
"""
VERSION = 'inliner-0.1-2016.08.16'
# VERSION = 'inliner-0.0-2014.10.19'
# VERSION = 'inliner-0.0-2014.07.15'
# VERSION = 'inliner-0.0-2014.12.24'    # CSeq-1.0beta
# VERSION = 'inliner-0.0-2014.10.31'    # CSeq-Lazy-0.6: newseq-0.6a, newseq-0.6c, SVCOMP15
# VERSION = 'inliner-0.0-2014.10.28'
# VERSION = 'inliner-0.0-2014.03.14'
# VERSION = 'inliner-0.0-2014.03.06 (CSeq-Lazy-0.2)'
# VERSION = 'inliner-0.0-2014.02.27'
# VERSION = 'inliner-0.0-2014.02.25'
# VERSION = 'inliner-0.0-2013.12.02'
# VERSION = 'inliner-0.0-2013.10.24-Gennaro-Omar'

"""

Transformations:
    - inlining of all the function calls,
      for functions which body is defined (except main() and __CSEQ_atomic_ functions)

    - renames main() to __cs_main_thread()

    - in threads:
        - pthread_exit;  are converted into  goto thread_exit;  (pthread_exit() argument is ignored)
        - return;  and  return value;  are converted into  goto thread_exit;  (return value is ignored)
        - local variables are converted into static local variables (to hold the value across context switches)


Prerequisites:
    - no function calls in if, while, for conditions (e.g. if(f(g)), while(cond), ...) ???
     (use module extractor.py)
    - no overlapping variable names as in regression testcase 102
     (use module varnames.py)


Limitations:
    - two function in the same expression, nested, e.g.: g(f(x));


TODO:
    - make nondet-static option work

    - limit recursion depth (otherwise parsing recursive functions will give a python stack overflow)

    - handle f(g(x)):  g(x) is in n.args therefore at the moment would not be inlined?


Changelog:
    2017.08.17  preserve return arguments and pthread_exit arguments for thread
    2016.12.20  accomplish todo 3 - rename labels (& corresponding gotos) in inlined blocks of code to avoid label duplication
    2016.12.02  add option to keep parameter passing atomically
    2016.10.05  don't want to use __cs_init_scalar on pthread types (see initVar function)
    2016.09.27  fix bug: problem of init dynamic size array
    2016.09.27  fix bug: multiple inline of two functions use the same (global) variable as parameter
    2016.09.16  add option to keep static array declaration (no cast to pointer)
    2016.08.16  __cs_init_scalar less ubiquitous
    2015.10.19  fix in _inlineFunction
    2015.07.16  fix inlining function in a label statement (Truc)
    2015.07.15  fixed linemapping for inlined function blocks + expanded parameter passing (Truc)
    2014.12.09  further code refactory to match the new organisation of the CSeq framework
    2014.10.31  bugfix: when dealing with expressions such as: if(!f(x)) would inline the function twice
    2014.10.28  inlining optimization: ....
    2014.03.14  further code refactory to match  module.Module  class interface
    2014.03.09  bugfix: external module  varnames.py  to fix regression overlapping variable names (see regression/102,103 )
    2014.03.06  bugfix: inliner wrong handling array as parameters (see regression/100_inline_struct_array.c)
    2014.02.27  improved indentation in inlined blocks
    2014.02.25  switched to  module.Module  base class for modules
    2013.12.02  bugfix: local struct variables not converted into static struct variables (e.g. struct a --> static struct a;)

"""

import copy, re
import pycparser.c_parser, pycparser.c_ast, pycparser.c_generator
from pycparser import c_ast
import core.common, core.module, core.parser, core.utils


# import sys #DEB

class inliner(core.module.Translator):
    functionlines = {}  # map function names to sets of line numbers
    linestofunctions = {}  # map from lines to function names

    ##__functionsToBeInlined = []     # ids of all the functions to be inlined
    currentFunction = ['']
    currentFunctionParams = []  # while parsing a function call, keeps the list of parameters used for the actual call

    inlinedStack = []  # inlined function to add before a statement
    # S: current index (= functionname_inliningcountforthisfunction) used for labels and gotos obtained from two following stacks
    functionStack = []  # stack of the function names
    indexStack = []  # stack of the counting value

    parametersToRemoveStack = [[]]
    switchTo = []  # Fix to avoid multiple inliner of two functions with take the same parameter (as a global var, pfscan)

    __parsingStruct = False  # Set to true when parsing a struct or union

    # old
    funcInlinedCount = {}  # number of times a function call has been inlined, by function
    funcInlinedLevel = {}  # number of levels in a function call unwinding

    recursivebound = 1  # same as unroll
    #
    keepstaticarray = False
    atomicparameter = False
    __globalMemoryAccessed = False
    __hasatomicbegin = False
    __canbemerged = {}

    __nondet_static = False

    # Keep return and pthread_exit of each thread
    __exit_args = {}

    local = 0  # S: added to handle differen versions of init of local vars
    inlineInfix = ''  # S: added to copy inlineInfix from env passed in loadfromstring

    currFuncPtrParamMap = {}  # keeps the value in the current call of the function parameters of type function pointer

    # we remove such parameters and inline the corresponding functions
    def init(self):
        self.addInputParam('keepstaticarray', 'keep static array, do not change to pointer version', '', False, True)
        self.addInputParam('atomicparameter', 'keep passing parameter atomic', '', False, True)
        self.addInputParam('nondet-static', 'use default backend support of nondet static variables', '', False, True)

    def loadfromstring(self, string, env):
        if self.getInputParamValue('keepstaticarray') is not None:
            self.keepstaticarray = True

        if self.getInputParamValue('atomicparameter') is not None:
            self.atomicparameter = True

        if 'unwind' in env.paramvalues:
            self.recursivebound = int(env.paramvalues['unwind'])

        if self.getInputParamValue('nondet-static') is not None:
            self.__nondet_static = True
        # DR
        if env.enableDR:
            self.local = env.local  # S
        self.inlineInfix = env.inlineInfix  # S

        super(self.__class__, self).loadfromstring(string, env)

    ''' Check whether or not the input source code has been fully inlined,
        i.e. whether every function defined in the original source code has been inlined,
        or the function inlining bound has been met.
    '''

    def inlined(self):
        pass

    def visit_UnaryOp(self, n):
        operand = self._parenthesize_unless_simple(n.expr)

        # print "N.OP     %s" % n.op
        # print "OPERAND: %s" % operand
        # print "STACK: %s" % str(self.parametersToRemoveStack[-1])
        # print (self.switchTo)

        #
        if n.op == 'p++':
            return '%s++' % operand
        elif n.op == 'p--':
            return '%s--' % operand
        elif n.op == 'sizeof':
            # Always parenthesize the argument of sizeof since it can be
            # a name.
            return 'sizeof(%s)' % self.visit(n.expr)
        elif n.op == '*' and len(self.switchTo) > 0 and operand in self.switchTo[-1]:
            return self.switchTo[-1][operand]
        else:
            return '%s%s' % (n.op, operand)

    def visit_Compound(self, n):
        s = self._make_indent() + '{\n'
        self.indent_level += 1

        ##print "COMPOUND %s START   " % (self.indent_level)

        if n.block_items:
            globalMemoryAccessed = False
            if len(self.currentFunction) > 0:
                self.__canbemerged[self.currentFunction[-1]] = False
            for stmt in n.block_items:
                '''
                if hasattr(stmt, 'coord'):
                    print "COORDS: %s" % (stmt.coord )
                else:
                    print "COORDS NO"
                '''
                self.__globalMemoryAccessed = False
                self.__hasatomicbegin = False
                k = self._inlineIfNeeded(stmt)
                globalMemoryAccessed = self.__globalMemoryAccessed
                if self.__hasatomicbegin and not globalMemoryAccessed and len(self.currentFunction) > 0:
                    self.__canbemerged[self.currentFunction[-1]] = True

                ##print "/ \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ /\n"
                #######print k
                ###print "\\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\ / \\\n"
                s += k

        ###print "COMPOUND %s END" % self.indent_level

        self.indent_level -= 1
        s += self._make_indent() + '}\n'

        return s

    def __isGlobal(self, f, v):
        if (v in self.Parser.varNames[''] and v not in self.Parser.varNames[f]):
            return True
        else:
            return False

    # S: added to handle var renaming in each inlining of functions
    def updateName(self, name):
        newname = ''
        if self.indexStack:
            newname = name.replace(self.inlineInfix, str(self.indexStack[-1]) + '_')
        else:
            newname = name.replace(self.inlineInfix, '')
        return newname

    def visit_ID(self, n):
        # If this ID corresponds either to a global variable,
        # or to a pointer...
        #
        if (self.__isGlobal(self.currentFunction[-1], n.name) and not
        n.name.startswith('__cs_thread_local_')):
            self.__globalMemoryAccessed = True

        name = self.updateName(n.name)
        # S: added to handle var renaming in each inlining of functions
        # name = n.name
        # if self.indexStack:
        #    name = name.replace(self.inlineInfix, str(self.indexStack[-1]) + '_')
        # else:
        #    name = name.replace(self.inlineInfix,'')
        ##S
        return name

    def visit_ExprList(self, n):
        visited_subexprs = []

        for expr in n.exprs:
            if isinstance(expr, pycparser.c_ast.ExprList):
                visited_subexprs.append('{' + self.visit(expr) + '}')
            else:
                visited_subexprs.append(self.visit(expr))

        if visited_subexprs not in self.currentFunctionParams:
            self.currentFunctionParams.append(visited_subexprs)

        return ', '.join(visited_subexprs)

    def visit_FuncDef(self, n):
        # Function definitions of inlined functions must disappear (except thread functions).
        #
        # if n.decl.name in self.__functionsToBeInlined and n.decl.name not in self.Parser.threadName:  OMAROMAROMAROMAR

        if self.____needsInlining(
                n.decl.name) and n.decl.name not in self.Parser.threadName and n.decl.name not in self.Parser.funcReferenced:
            ##return 'int __cs_function_%s_inlined = 1;\n' % n.decl.name;
            return ''

        self.currentFunction.append(n.decl.name)

        decl = self.visit(n.decl)
        self.indent_level = 0
        body = self.visit(n.body)

        # At the bottom of each thread, add a pthread_exit() statement
        #
        returnStmt = ''

        if (self.currentFunction[-1] in self.Parser.threadName or self.currentFunction[-1] == 'main'):
            if self.currentFunction[-1] not in self.__exit_args:
                self.__exit_args[self.currentFunction[-1]] = '0'
            returnStmt = self.INDENT_SPACING + '__exit_%s: ; %s(%s);\n' % (
                self.currentFunction[-1],
                core.common.changeID['pthread_exit'],
                self.__exit_args[self.currentFunction[-1]])

        # Continue the visit.
        if n.param_decls:
            knrdecls = ';\n'.join(self.visit(p) for p in n.param_decls)
            body = body[:body.rfind('}')] + self._make_indent() + returnStmt + '}'
            block = decl + '\n' + knrdecls + ';\n' + body + '\n'
        else:
            body = body[:body.rfind('}')] + self._make_indent() + returnStmt + '}'
            block = decl + '\n' + body + '\n'

        if (self.currentFunction[-1] in self.Parser.threadName or self.currentFunction[-1] == 'main'):
            # and len(self.currentFunction) == 2 :   #S: len(self.currentFunction) == 2 tests that we are at the top level
            self.funcInlinedCount = {}  # S: reset count of all inlined functions, next thread will use fresh counters
        self.currentFunction.pop()

        return block

    ''' Labels in inlined function needs to be renamed, the label needs to be unique in a function scope
        TRUC: todo 3
    '''

    def visit_Goto(self, n):
        if len(self.currentFunction) > 0 and self.____needsInlining(self.currentFunction[-1]):
            # truc's version#truc's version            count = 0 if self.currentFunction[-1] not in self.funcInlinedCount else self.funcInlinedCount[self.currentFunction[-1]] - 1
            # truc's version#truc's version            newlabel = n.name + '_' + self.currentFunction[-1] + '_' + str(count)
            # S: above truc's version changed as:
            if self.indexStack:
                newlabel = n.name + '_' + self.functionStack[-1] + '_' + str(self.indexStack[-1])
            else:
                newlabel = n.name + '_' + self.currentFunction[-1] + '_0'

            return 'goto ' + newlabel + ';'
        else:
            return 'goto ' + n.name + ';'

    '''
    '''

    def visit_FuncCall(self, n):
        self.currentFunctionParams = []

        fref = self._parenthesize_unless_simple(n.name)

        # print "function call: %s" % fref
        # print "stack: %s" % str(self.stack)
        # print "\n\n"

        # Pthread exit()s can only be within thread functions,
        # no need to check whether we're in a thread.
        #
        if fref == core.common.changeID['pthread_exit']:
            args = self.visit(n.args)
            self.__exit_args[self.currentFunction[-1]] = args
            # print self.currentFunction
            return 'goto __exit_%s ' % (self.currentFunction[
                1])  # S: old (self.currentFunction[-1]), thread name is the name at the bottom of currentFunction stack

        if fref == '__CSEQ_atomic_begin':
            self.__hasatomicbegin = True

        args = self.visit(n.args)

        s = fref + '(' + args + ')'

        if n.args is None:
            self.currentFunctionParams.append([])

        # print (fref),
        # print (self.currFuncPtrParamMap),
        # print self.____needsInlining(fref)
        if self.____needsInlining(fref):
            if fref in self.currFuncPtrParamMap:
                fref = self.currFuncPtrParamMap[fref]
            if fref not in self.funcInlinedCount:
                self.funcInlinedCount[fref] = 0
                self.funcInlinedLevel[fref] = 0  # S: reset levels
            self.funcInlinedCount[fref] += 1
            self.funcInlinedLevel[fref] += 1  # S: keep track of levels, one level up
            self.indexStack.append(self.funcInlinedCount[fref])
            self.functionStack.append(fref)
            # print 'Current top Function: ' + self.currentFunction[1] + ' Function: ' + fref + ' Level: ' + str(self.funcInlinedLevel) +'  Count: '+ str(self.funcInlinedCount) + '  index: ' + str(self.indexStack)

            reachBound = False
            if fref in self.functionStack[:-1] and self.funcInlinedLevel[fref] > self.recursivebound:
                self.inlinedStack[-1] += '__CSEQ_assume(0);\n'  # Stop execution
                reachBound = True
            else:
                # print fref ; print self.currFuncPtrParamMap  #QUI
                # n.show()
                self.inlinedStack[-1] += (self._inlineFunction(self.Parser.funcASTNode[fref], n, False)) + '\n'

            if self.Parser.funcIsVoid[fref]:
                s = 'DELETETHIS'  # S: deletes just the line where the return value should be assigned
            else:
                if reachBound:
                    index = len(self.functionStack) - 2 - ((self.functionStack[:-1])[::-1]).index(fref)
                    #    tempIndex = '_%s_%s' % (fref, self.funcInlinedCount[fref] - 1)
                    #    s = '__cs_retval_%s' % tempIndex
                    #    # reset inline count
                    #    #self.funcInlinedCount[fref] =0  #S: replaced by decreasing counter on returning
                    s = '__cs_retval_%s_%s' % (fref, self.indexStack[
                        index])  # S: this is needed if function is not void, and is a fake assignment, will never occur and choice of var to assign is safe in the sense that it is of the same type of the return value and is certainly declared at this point.
                    self.funcInlinedCount[fref] -= 1  # S: decrease by 1 the counter since this call is not done

                else:
                    s = '__cs_retval_%s_%s' % (self.functionStack[-1], self.indexStack[-1])
            self.indexStack.pop()
            self.functionStack.pop()
            self.funcInlinedLevel[fref] -= 1  # S: decrease  such that we unwind for levels and not occurences of calls
            # if self.funcInlinedLevel[fref] == 0:  self.funcInlinedCount[fref] =0  #S: reset count if we ended unrolling of fref

        return s

    '''
    '''
    '''
    def visit_Return(self, n):
        if self.currentFunction[-1] in self.Parser.threadName:
            return 'goto __exit_%s; /* return stmt */' % (self.currentFunction[-1])
            #return 'goto _RETURN_exit_%s_%s;' % (self.currentFunction, self.funcInlinedCount[self.currentFunction])
        elif self.currentFunction[-1] == 'main':
            return 'goto __exit_main;  /* return stmt in main() */'

        s = 'return'
        if n.expr: s += ' ' + self.visit(n.expr)

        return s + ';'
    '''

    def visit_Return(self, n):
        if len(self.indexStack) > 0:
            if self.Parser.funcIsVoid[self.currentFunction[-1]]:
                return 'goto __exit_%s_%s;' % (self.functionStack[-1], self.indexStack[-1])  # void
            else:
                return '__cs_retval_%s_%s = %s; goto __exit_%s_%s;' % (
                self.functionStack[-1], self.indexStack[-1], self.visit(n.expr), self.functionStack[-1],
                self.indexStack[-1])  # non-void

        if self.currentFunction[-1] in self.Parser.threadName:
            args = self.visit(n.expr) if n.expr else '0'
            self.__exit_args[self.currentFunction[-1]] = args
            return 'goto __exit_%s; ' % (self.currentFunction[-1])
        elif self.currentFunction[-1] == 'main':
            self.__exit_args[self.currentFunction[-1]] = '0'
            return 'goto __exit_main; '

        s = 'return'
        if n.expr: s += ' ' + self.visit(n.expr)
        return s + ';'

    ''' TODO: labels inside inlined functions must be indexed using  indexStack
    '''
    '''
    def visit_Label(self, n):
        if self.currentFunction in self.__functionsToBeInlined:
            return n.name + self.indexStack[-1] + ':\n' + self._generate_stmt(n.stmt)
        else:
            return n.name + ':\n' + self._generate_stmt(n.stmt)
    '''

    ''' TODO gotos-to-labels inside inlined functions must be indexed using  indexStack
    '''
    '''
    def visit_Goto(self, n):
        if self.currentFunction in self.__functionsToBeInlined:
            return 'goto ' + n.name + self.indexStack[-1] + '; /* updated label index from previous goto stmt */'
        else:
            return 'goto ' + n.name + ';'
    '''

    def visit_Struct(self, n):
        #
        oldParsingStruct = self.__parsingStruct
        self.__parsingStruct = True
        s = self._generate_struct_union_enum(n, 'struct')
        self.__parsingStruct = oldParsingStruct

        return s

    def visit_Union(self, n):
        #
        oldParsingStruct = self.__parsingStruct
        self.__parsingStruct = True
        s = self._generate_struct_union_enum(n, 'union')
        self.__parsingStruct = oldParsingStruct

        return s

    @staticmethod
    def _initVar(varType, varName, varTypeUnExpanded):
        s = ''
        if varType == 'int':
            s = '%s = __CSEQ_nondet_int()' % varName
        elif varType == 'unsigned int':
            s = '%s = __CSEQ_nondet_uint()' % varName
        elif varType == '_Bool' or varType == 'bool':
            s = '%s = __CSEQ_nondet_bool()' % varName
        elif varType == 'char':
            s = '%s = __CSEQ_nondet_char()' % varName
        elif varType == 'unsigned char':
            s = '%s = __CSEQ_nondet_uchar()' % varName
        elif varType == 'unsigned long':
            s = '%s = __CSEQ_nondet_uint()' % varName
        elif varType == '__cs_t':
            s = ''
        elif varType == '__cs_mutex_t':
            s = ''
        elif varType == '__cs_cond_t':
            s = ''
        elif varType == '__cs_barrier_t':
            s = ''
        elif varType == '__cs_attr_t':
            s = ''

        else:
            s = '__cs_init_scalar(&%s, sizeof(%s))' % (varName, varType)
        return s

    def _hasBeenAssignedLater(self, varname):
        # There is case where a variable does not need an nondet assignment
        # 1. There is an immediate assign statement after the declaration of variable
        # 2. This variable is created in the sack of for loop
        # --> the two cases above can be compacted into one case: there is an assignment to variable after this
        if (len(self.currentFunction) > 0 and
                self.currentFunction[-1] != '' and
                self.currentFunction[-1] in self.Parser.varNoNeedInit and
                varname in self.Parser.varNoNeedInit[self.currentFunction[-1]]):
            return True
        return False

    def _needInit(self, varname):
        if ('__cs_switch_cond' in varname or  # from switchtransformer.py
                '__cs_tmp_if_cond_' in varname or  # from extractor.py
                '__cs_tmp_while_cond_' in varname or  # from extractor.py
                '__cs_tmp_for_cond_' in varname or  # from extractor.py
                '__cs_dowhile_onetime_' in varname or  # from remover.py
                self._hasBeenAssignedLater(varname)):
            return False
        return True

    def visit_Decl(self, n, no_type=False):
        # no_type is used when a Decl is part of a DeclList, where the type is
        # explicitly only for the first delaration in a list.
        #

        s = n.name if no_type else self._generate_decl(n)
        # S: added to handle var renaming in each inlining of functions

        s = self.updateName(s)
        name = self.updateName(str(n.name))

        # name = ''
        # if self.indexStack:
        #    s = s.replace(self.inlineInfix, str(self.indexStack[-1]) + '_')
        #    name = str(n.name).replace(self.inlineInfix, str(self.indexStack[-1]) + '_')
        # else:
        #    s = s.replace(self.inlineInfix,'')
        #    name = str(n.name).replace(self.inlineInfix,'')

        if n.bitsize:
            s += ' : ' + self.visit(n.bitsize)
        # S: added to handle declaration of constant variables or struct def with no variables declared, no transformation is required.
        if "const" in s.split() or n.name == None:
            if n.init:
                processInit = True
                if isinstance(n.init, c_ast.InitList):
                    s += ' = {' + self.visit(n.init) + '}'
                elif isinstance(n.init, c_ast.ExprList):
                    s += '= (' + self.visit(n.init) + ')'
                else:
                    s += '= ' + self.visit(n.init)
            return s
        # S: end addition

        # Change local variables to be static vars,
        # needed for this particular encoding to remember the old values of local variables
        # between simulated context switches.
        #
        # If the variable is scalar or it is an array of fixed size, then just add  static  to its declaration.
        # If the variable is an array of non fixed size, then change it to a static pointer and adds a call to malloc() to complete the initialization,
        # (e.g.    int x[size];  -->  static int * x; x = (int *)malloc(sizeof(int)*size);  )
        #
        # TODO: init_scalar()/malloc() should not be called when variables have init expressions!
        #
        processInit = False  # Has processed the init expression
        if (isinstance(n, c_ast.Decl) and  # it is a declaration
                self.currentFunction[-1] != '' and  # Not a global declaration
                self.indent_level > 0 and  # This is needed to rule out function decls
                not s.startswith('static ') and  # This may not usefull
                not self.__parsingStruct):  # and not part of a struct or union
            if ((self.__isScalar(self.currentFunction[-1], n.name) or
                 self.__isStruct(self.currentFunction[-1], n.name))):  # and
                # not self.Parser.varInitExpr[self.currentFunction[-1], n.name]):
                s = 'static ' + s  # declaration
                if n.init:  # This variables has Init expression
                    processInit = True
                    if isinstance(n.init, c_ast.InitList):
                        s += ' = {' + self.visit(n.init) + '}'
                    elif isinstance(n.init, c_ast.ExprList):
                        s += '; %s = (' % name + self.visit(n.init) + ')'  # S: n.name --> name
                    else:
                        s += '; %s = ' % name + self.visit(n.init)  # S: n.name --> name
                else:  # no init
                    if self.__isScalar(self.currentFunction[-1], n.name):
                        varType = self.Parser.varType[self.currentFunction[-1], n.name]
                        varTypeUnExpanded = self.Parser.varTypeUnExpanded[self.currentFunction[-1], n.name]
                        initialStmt = '; ' + self._initVar(varType, name, varTypeUnExpanded) if self._needInit(
                            n.name) and self.local in range(0, 2) else ''  # S: n.name --> name
                        s += initialStmt
                    #                   elif self.__isStruct(self.currentFunction[-1], n.name):
                    #                       s += ''
                    else:  ## what can it be?
                        if self.local in range(0, 2):
                            s += '; __cs_init_scalar(&%s, sizeof(%s))' % (
                                name, self.Parser.varType[self.currentFunction[-1], n.name])

            #            elif (self.__isScalar(self.currentFunction[-1], n.name) and
            #                    # Do not believe this check, it is not always true???
            #                    self.Parser.varInitExpr[self.currentFunction[-1], n.name]):
            #                s = 'static ' + s
            #                if n.init:
            #                    processInit = True
            #                    if isinstance(n.init, c_ast.InitList):
            #                        s += ' = {' + self.visit(n.init) + '}'
            #                    elif isinstance(n.init, c_ast.ExprList):
            #                        s += '; %s = (' % n.name + self.visit(n.init) + ')'
            #                    else:
            #                        s += '; %s = ' % n.name + self.visit(n.init)
            #                else:
            #                    varType = self.Parser.varType[self.currentFunction[-1], n.name]
            #                    varTypeUnExpanded = self.Parser.varTypeUnExpanded[self.currentFunction[-1], n.name]
            #                    initialStmt = '; ' + self._initVar(varType, n.name, varTypeUnExpanded) if self._needInit(n.name) and self.local in range(0,2) else ''
            #                    s += initialStmt
            #
            elif self.__isArray(self.currentFunction[-1], n.name):
                # There are two cases:
                # 1. this array has a constant expression of compound literal
                # 2. anything else
                init = ''
                initType = 0
                if n.init:
                    processInit = True
                    if isinstance(n.init, c_ast.InitList):
                        init = ' = {' + self.visit(n.init) + '}'
                        initType = 1
                    elif isinstance(n.init, c_ast.ExprList):
                        init = ' = (' + self.visit(n.init) + ')'
                        initType = 0
                    else:
                        init = ' = ' + self.visit(n.init)
                        initType = 0

                if initType == 1:
                    # Case 1
                    s = 'static ' + s + init
                else:
                    # Anything else
                    if processInit:
                        if self._is_dynamic_size_array(self.currentFunction[-1], n.name):
                            s = 'static ' + s + init
                        else:
                            s = 'static ' + s + '; %s' % name + init  # S: n.name --> name
                    else:
                        if self.keepstaticarray:
                            s = 'static ' + s
                        else:
                            stars = '*' * self.Parser.varArity[self.currentFunction[-1], n.name]
                            vartype = self.Parser.varType[self.currentFunction[-1], n.name]
                            s = 'static %s %s %s; ' % (vartype, stars, name)  # S: n.name --> name
                            # S: init local vars
                            if self.init == 1:
                                s += '__cs_init_scalar(& %s, (sizeof(%s)*%s));' % (
                                name, vartype, self._totalSize(self.currentFunction[-1], n.name))  # S: n.name --> name
                            elif self.init == 0:
                                s += n.name + ' = (%s %s) %s(sizeof(%s)*%s)' % (
                                vartype, stars, core.common.changeID['malloc'], vartype,
                                self._totalSize(self.currentFunction[-1],
                                                name))  # S: original transf.  #S: n.name --> name
            else:  # Anything else, Truc's modification
                init = ''
                initType = 0
                if n.init:
                    processInit = True
                    if isinstance(n.init, c_ast.InitList):
                        init = ' = {' + self.visit(n.init) + '}'
                        initType = 1
                    elif isinstance(n.init, c_ast.ExprList):
                        init = ' = (' + self.visit(n.init) + ')'
                        initType = 0
                    else:
                        init = ' = ' + self.visit(n.init)
                        initType = 0
                if initType == 1:
                    s = 'static ' + s + init
                else:
                    if processInit:
                        if self._is_dynamic_size_array(self.currentFunction[-1], n.name):
                            s = 'static ' + s + init
                        else:
                            s = 'static ' + s + '; %s' % name + init  # S: n.name --> name
                    else:
                        if self.local in range(0, 2):
                            s = 'static ' + s + '; __cs_init_scalar(&%s, sizeof(%s))' % (
                                name, self.Parser.varType[self.currentFunction[-1], n.name])  # S: n.name --> name

        # Global variables and already static variables
        if n.init and not processInit:
            if isinstance(n.init, c_ast.InitList):
                s += ' = {' + self.visit(n.init) + '}'
            elif isinstance(n.init, c_ast.ExprList):
                s += ' = (' + self.visit(n.init) + ')'
            else:
                s += ' = ' + self.visit(n.init)

        return s

    ''' OMAR CODE
    def visit_Decl(self, n, no_type=False):
        # no_type is used when a Decl is part of a DeclList, where the type is
        # explicitly only for the first delaration in a list.
        #
        s = n.name if no_type else self._generate_decl(n)

        if n.bitsize: s += ' : ' + self.visit(n.bitsize)

        # Change local variables to be static vars,
        # needed for this particular encoding to remember the old values of local variables
        # between simulated context switches.
        #
        # If the variable is scalar or it is an array of fixed size, then just add  static  to its declaration.
        # If the variable is an array of non fixed size, then change it to a static pointer and adds a call to malloc() to complete the initialization,
        # (e.g.    int x[size];  -->  static int * x; x = (int *)malloc(sizeof(int)*size);  )
        #
        # TODO: init_scalar()/malloc() should not be called when variables have init expressions!
        #

        nondet_function = {}
        nondet_function['int'] = "__CSEQ_nondet_int()"
        nondet_function['unsigned int'] = "__CSEQ_nondet_uint()"
        nondet_function['_Bool'] = "__CSEQ_nondet_bool()"
        nondet_function['char'] = "__CSEQ_nondet_char()"
        nondet_function['unsigned char'] = "__CSEQ_nondet_uchar()"

        if (isinstance(n, c_ast.Decl) and
            self.currentFunction[-1] != '' and
            self.indent_level > 0 and
            not s.startswith('static ') and
            not self.__parsingStruct):

            if (self.__isScalar(self.currentFunction[-1], n.name) or self.__isStruct(self.currentFunction[-1], n.name)) and not self.Parser.varInitExpr[self.currentFunction[-1], n.name]:
            #if self.__isScalar(self.currentFunction[-1], n.name) and not self.Parser.varInitExpr[self.currentFunction[-1], n.name]:
                vartype = self.Parser.varType[self.currentFunction[-1], n.name]
                # if vartype not in ("int", "unsigned int", "_Bool", "char", "unsigned char", ):
                s = 'static ' + s + '; __cs_init_scalar(&%s, sizeof(%s))' % (n.name, vartype)
                # else:
                    # s = 'static ' + s + '; %s = %s' % (n.name, nondet_function[vartype])
                #s = 'static ' + s + '; malloc(&%s, sizeof(%s))' % (n.name, self.Parser.varType[self.currentFunction[-1], n.name])
            elif self.__isScalar(self.currentFunction[-1], n.name) and self.Parser.varInitExpr[self.currentFunction[-1], n.name]:
                s = 'static ' + s
            elif self.__isArray(self.currentFunction[-1], n.name):
                stars = '*' * self.Parser.varArity[self.currentFunction[-1], n.name]
                vartype = self.Parser.varType[self.currentFunction[-1],n.name]

                s = 'static %s %s %s; ' % (self.Parser.varType[self.currentFunction[-1], n.name], stars, n.name)
                s += n.name + ' = (%s %s)malloc(sizeof(%s)*%s); __CSEQ_assume(%s)' % (vartype, stars, vartype, self._totalSize(self.currentFunction[-1], n.name), n.name)

        if n.init:
            if isinstance(n.init, c_ast.InitList):
                s += ' = {' + self.visit(n.init) + '}'
            elif isinstance(n.init, c_ast.ExprList):
                s += ' = (' + self.visit(n.init) + ')'
            else:
                s += ' = ' + self.visit(n.init)

        return s

    '''

    # def visit_Label(self, n):
    #     # Truc (method 1: simply add an empty statement)
    #     return n.name + ':;\n' + self._generate_stmt(n.stmt)

    ########################################################################################

    def _inlineIfNeeded(self, stmt):
        # Truc comment this for method 2
        # self.inlinedStack.append('')

        # original = self._generate_stmt(stmt)
        # original = original.replace('DELETETHIS;\n', '')
        # original = self.inlinedStack[-1] + original

        # self.inlinedStack.pop()

        # Truc (method 2: Identify inlined function call by inlinedStacked
        # and change things according to type of statements)
        self.inlinedStack.append('')
        original = ''
        if isinstance(stmt, pycparser.c_ast.Label):
            label = stmt.name
            # TRUC, todo 3
            if len(self.currentFunction) > 0 and self.____needsInlining(self.currentFunction[-1]):
                # S: line below changes the truc's version
                if self.indexStack:
                    label = label + '_' + self.functionStack[-1] + '_' + str(self.indexStack[-1])
                else:
                    label = label + '_' + self.currentFunction[-1] + '_0'
            # truc's version                count = 0 if self.currentFunction[-1] not in self.funcInlinedCount else self.funcInlinedCount[self.currentFunction[-1]] - 1
            # truc's version                label = label +'_' + self.currentFunction[-1] + '_' + str(count)
            original = self._generate_stmt(stmt.stmt)
            if self.inlinedStack[-1] == '':  # If this statement doesn't contain inlined function
                original = label + ':\n' + original
            else:
                original = re.sub('(DELETETHIS;\n)|(DELETETHIS;)', '', original)
                # original = original.replace('(DELETETHIS;\n)', '')
                original = original.replace('(DELETETHIS)',
                                            '0')  # S: added to handle cases when the function call is part of an expression
                # original = re.sub('(DELETETHIS;\n)|(DELETETHIS)', '', original)
                original = label + ':;\n' + self.inlinedStack[-1] + original
        else:
            original = self._generate_stmt(stmt)
            original = re.sub('(DELETETHIS;\n)|(DELETETHIS;)', '', original)
            # original = original.replace('DELETETHIS;\n', '')
            original = original.replace('DELETETHIS',
                                        '0')  # S: added to handle cases when the function call is part of an expression
            # original = re.sub('(DELETETHIS;\n)|(DELETETHIS)', '', original)
            original = self.inlinedStack[-1] + original
        self.inlinedStack.pop()

        return original

    ''' Generate the function body,
        for either including it in a function definition, or
        for inserting it into a statement
    '''

    def _inlineFunction(self, n, fcall_ast_node, simple):
        # S: added to handle proper treatment of function parameters of type pointer to function
        oldmap = self.currFuncPtrParamMap
        self.currFuncPtrParamMap = {}
        # S:
        fInput = fOutput = ''
        fref = n.decl.name
        # print "inlining function:%s %s" % (fref, str(self.currentFunctionParams))
        # Simulate input parameter passing.
        #
        # Build argument initialization statement(s) if needed, to simulate parameter passing
        # (see transformation details below)
        #
        # args = self.visit(fcall_ast_node.args)  # ?????

        # Analysis of function-call parameters
        #
        self.parametersToRemoveStack.append([])
        self.switchTo.append({})

        if fcall_ast_node.args is not None:
            paramNo = -1

            #
            #
            for expr in fcall_ast_node.args.exprs:  # for each parameter in the function call
                paramNo += 1
                if (isinstance(expr, pycparser.c_ast.UnaryOp) and
                        expr.op == '&' and
                        expr.expr.name not in self.Parser.varNames[self.currentFunction[-1]] and
                        expr.expr.name in self.Parser.varNames[''] and
                        len(self.Parser.varOccurrence[fref, self.Parser.funcParams[fref][paramNo]]) - len(
                            self.Parser.varDeReferenced[fref, self.Parser.funcParams[fref][paramNo]]) == 0):
                    # print "varname: %s     currentscope:%s    currentfinlined:%s    parameterno:%s" % (expr.expr.name, self.currentFunction[-1], fref, paramNo)
                    # print "variable %s is global and referenced!!" % expr.expr.name
                    # print "the corrseponding function parameter is %s" % (self.Parser.funcParams[fref][paramNo])
                    # print "is it always dereferenced? %s %s" % (len(self.Parser.varOccurrence[fref, self.Parser.funcParams[fref][paramNo]]), len(self.Parser.varDeReferenced[fref,self.Parser.funcParams[fref][paramNo]]) )
                    # print "\n"
                    # exit(12345)
                    ##print "REMOVE reference to global variable '&%s' from the fuction call!!!!" % expr.expr.name
                    self.parametersToRemoveStack[-1].append(
                        '&' + expr.expr.name)  # parameter  expr.expr.name  in the call to  fref()  can to be removed
                    # print "IN THE FUNCTION BODY CHANGE (*%s) -> %s" % (self.Parser.funcParams[fref][paramNo], expr.expr.name)
                    pname = self.updateName(self.Parser.funcParams[fref][
                                                paramNo])  # S: added to handle var renaming in each inlining of functions
                    # pname=''
                    self.switchTo[-1][pname] = expr.expr.name
                    # self.switchTo[-1][self.Parser.funcParams[fref][paramNo]] = expr.expr.name

            # if fcall_ast_node.args is not None:
            i = 0

            for p in self.Parser.varNames[fref]:
                # S: added to handle var renaming in each inlining of functions
                pname = ''
                if self.indexStack:
                    pname = p.replace(self.inlineInfix, str(self.indexStack[-1]) + '_')
                else:
                    pname = p.replace(self.inlineInfix, '')
                # S
                # print pname
                if self.Parser.varKind[fref, p] == 'p':
                    # print "parameters to remove %s" % str(self.parametersToRemoveStack[-1])
                    # print "p = %s" % p
                    # print "\n\n"
                    if self.currentFunctionParams[-1][i] in self.parametersToRemoveStack[-1]:
                        i += 1
                        # print( self.currentFunctionParams[-1][i-1])
                        # print(self.parametersToRemoveStack[-1])
                        # print pname
                        continue  # this parameter is not needed
                    if not self.__isPointerToFunction(fref, p) and not self.__isArray(fref, p):
                        ##print "    p       %s " % p
                        ##print "    fref    %s" % fref
                        ##print "    type    %s" % self.Parser.varTypeUnExpanded[fref,p]
                        ##print "    param   %s\n" % self.currentFunctionParams[-1][i]

                        # S: then branch added to handle constant params properly
                        if 'const' in self.Parser.varTypeUnExpanded[fref, p]:
                            fInput += 'static %s %s = %s; ' % (
                            self.Parser.varTypeUnExpanded[fref, p], pname, self.currentFunctionParams[-1][i])
                        else:
                            fInput += 'static %s %s; %s = %s; ' % (
                            self.Parser.varTypeUnExpanded[fref, p], pname, pname, self.currentFunctionParams[-1][i])
                        i += 1
                    elif not self.__isPointerToFunction(fref, p) and self.__isArray(fref, p):
                        varSize = ''
                        stars = ''
                        '''
                        for s in self.Parser.varSize[fref,p]:
                            if s != -1: varSize += '[%s]' % s
                            else: varSize += '[]'
                        '''
                        for s in self.Parser.varSize[fref, p]:
                            varSize += '[%s]' % (s if s != -1 else '')

                        # S: pre-debian, changed stars--> varSize to handle parameters  of type 'int (* x) [10]' i.e., pointers to array type
                        #                        for s in self.Parser.varSize[fref,p]:
                        #                            #varSize += '[%s]' % (s if s != -1 else '')
                        #                            #####varSize += '[]'   # ignore the size for array passed as function parameters
                        #                            stars += '*'

                        #####fInput += 'static %s %s%s; %s = %s; ' % (self.Parser.varTypeUnExpanded[fref,p], p, varSize, p, self.currentFunctionParams[-1][i])
                        x = self.Parser.varTypeUnExpanded[fref, p].replace('(*)',
                                                                           '(*%s)' % p)  # S: added non in pre-debian
                        # fInput += 'static %s %s; %s = %s; ' % (self.Parser.varTypeUnExpanded[fref,p], varSize,  p, self.currentFunctionParams[-1][i])
                        fInput += 'static %s %s; %s = %s; ' % (x, varSize, pname, self.currentFunctionParams[-1][i])
                    # S: pre-debian changed stars--> varSize to handle parameters  of type 'int (* x) [10]' i.e., pointers to array type
                    #                        fInput += 'static %s %s%s; %s = %s; ' % (self.Parser.varTypeUnExpanded[fref,p], stars, p, p, self.currentFunctionParams[-1][i])
                    else:
                        #                x = self.Parser.varTypeUnExpanded[fref,p].replace('(*)', '(*%s)' % p)
                        # S: added to handle var renaming in each inlining of functions
                        #                if self.indexStack:
                        #                    x = x.replace(self.inlineInfix, str(self.indexStack[-1]) + '_')
                        #                else:
                        #                    x= x.replace(self.inlineInfix,'')
                        # S
                        # fInput += 'static %s; %s = %s; ' % (x, pname, self.currentFunctionParams[-1][i])
                        self.currFuncPtrParamMap[pname] = self.removeCasting(self.currentFunctionParams[-1][
                                                                                 i])  # S: replace above lines, parameter disappears from code and just save value for inlining at the function call

                        # print self.currFuncPtrParamMap
                        i += 1

        # Simulate output parameter returning.
        #

        if not self.Parser.funcIsVoid[fref]:
            fOutput = 'static %s __cs_retval_%s_%s;\n' % (
            self.Parser.funcBlockOut[fref], self.functionStack[-1], self.indexStack[-1])
        else:  # simple function call without assignment (e.g. f(x);)
            fOutput = ''
        # Truc - dirty fix, just inlude the line map of that function call
        fOutput = self._getCurrentCoords(fcall_ast_node) + '\n' + fOutput

        # Transform the function body by:
        #
        #   1. adding the initialization statement(s) (if any) at the top
        #   2. adding one exit label at the bottom where to jump to in order to simulate return statements
        #   3. change return statements to goto statements pointing to the exit label added in previous step
        #   4. all the rest is unchanged
        #

        # body (adds one indent each line)
        self.currentFunction.append(fref)
        # inlined = self._shiftIndent(self.visit(self.Parser.funcASTNode[fref].body))

        # save  copy of old lines so we may revert it back,
        # this removes the elements added while inlining,
        # otherwise when inlining the same function more than once,
        # the linemapping is only generated on the first inlined function call.
        oldlines = self.lines.copy()
        # self.Parser.funcASTNode[fref].body.show()
        inlined = self.visit(self.Parser.funcASTNode[fref].body)
        self.functionlines[fref] = self.lines - oldlines
        self.lines = oldlines

        # top
        # ~inlined = inlined.replace(self.INDENT_SPACING+'{', '/*** INLINING START %s ***********************************/\n' % fref + self.INDENT_SPACING + fOutput + self._make_indent() +'{\n' + self._make_indent() + fInput, 1)
        inlined = inlined[inlined.find('{') + 1:]
        if self.atomicparameter:
            fInput = '__CSEQ_atomic_begin();' + fInput
            if fref in self.__canbemerged and self.__canbemerged[fref]:
                inlined = inlined.replace('__CSEQ_atomic_begin()', '', 1)
            else:
                fInput += '__CSEQ_atomic_end();'

        addedheader = self.INDENT_SPACING + fOutput + self._make_indent() + '{\n' + self._make_indent(1) + fInput
        inlined = addedheader + inlined
        # print inlined

        # bottom
        inlined = inlined[:inlined.rfind('}')] + '%s __exit_%s_%s: ;  \n' % (
        self._make_indent(1), self.functionStack[-1], self.indexStack[-1]) + self._make_indent() + '}\n'
        # ~inlined += '\n' + self._make_indent() + '/*** INLINING END %s **************************************/' % fref

        self.parametersToRemoveStack.pop()
        self.switchTo.pop()
        self.currentFunction.pop()

        # S: restore  old map
        self.currFuncPtrParamMap = oldmap
        return inlined

    # Shift one indent each line.
    #
    def _shiftIndent(self, s):
        new = ''

        for line in s.splitlines():
            new += self.INDENT_SPACING + line + '\n'

        return new

    ''' Check whether variable  v  from function  f  has a fixed size,
        or not (e.g.  int x[expr]   with expr not constant.
    '''

    def _hasFixedSize(self, f, v):
        if self.Parser.varArity[f, v] > 0:
            for i in range(0, self.Parser.varArity[f, v]):
                if not self.Parser.varSize[f, v][i].isdigit():
                    return False

        return True

    ''' Return the total size of a given array in a string,
        as the expression of the product of all sizes.

        For example:

            int x[10][expr][3];

        returns:

            size = 10*(expr)*30;
    '''

    def _totalSize(self, f, v):
        sizeExpression = ''

        for i in range(0, self.Parser.varArity[f, v]):
            # if self.Parser.varSize[f,v][i].isdigit():     # simple digit
            sizeExpression += str(self.Parser.varSize[f, v][i]) + '*'

        sizeExpression = sizeExpression[:-1]

        return sizeExpression

    # Checks whether variable  v  from function  f  is an array.
    #
    def __isArray(self, f, v):
        # if f == 'main' and v == '__cs_nondetmain_c':  #DEB
        #   for x,y in  self.Parser.varArity: 
        #      if x==f: print "(%s,%s) : %s" % (f,y,self.Parser.varArity[f,y])
        #   sys.exit(0)
        if self.Parser.varArity[f, v] > 0:
            return 1
        else:
            return 0

    # Checks whether variable  v  from function  f  is scalar.
    # TODO redo properly at parser-level
    #
    def __isScalar(self, f, v):
        if (f, v) not in self.Parser.varArity or (f, v) not in self.Parser.varType: return 0

        if self.Parser.varArity[f, v] == 0 and not self.Parser.varType[f, v].startswith('struct ') and not \
        self.Parser.varType[f, v].startswith('union '):
            return 1
        else:
            return 0

    # Checks whether variable  v  from function  f  is a struct or a union.
    # TODO redo properly at parser-level
    #
    def __isStruct(self, f, v):
        result = 0
        if (f, v) in self.Parser.varType:
            if self.Parser.varType[f, v].startswith('struct ') or self.Parser.varType[f, v].startswith('union '):
                result = 1

        return result

    def __isPointerToFunction(self, f, v):
        if (f, v) in self.Parser.varPtrToFunct:
            return True
        else:
            return False
        # if '(*)' in self.Parser.varType[f,v]: return True
        # else: return False

    ''' Check whether function  f  needs to be inlined.
    '''

    def ____needsInlining(self, f):
        b = False
        if self.currFuncPtrParamMap and f in self.currFuncPtrParamMap.values():
            b = True
        return (b or
                (f in self.Parser.funcName and  # defined functions need to be inlined when called (if at all)
                 not f.startswith('__CSEQ_atomic') and
                 not f == '__CSEQ_assert' and
                 f != '' and
                 f != 'main'))

    def _is_dynamic_size_array(self, f, v):
        if (f, v) not in self.Parser.varID:
            return False

        if self.Parser.varArity[f, v] == 1 and self.Parser.varSize[f, v][0] == -1:
            return True

        return False

    def removeCasting(self, str):
        while str.endswith(')') or str.endswith(' '):
            str = str[:-1]
        list = str.split()
        return list[-1]
