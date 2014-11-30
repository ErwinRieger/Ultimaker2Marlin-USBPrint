#ifndef DELEGATE_H
#define DELEGATE_H

#include <stddef.h>
/* Here be dragons... */

template<typename A0=void, typename A1=void>
class delegate
{
public:
    delegate() : object_ptr(NULL), stub_ptr(NULL)
    {
    }

    template <class T, void (T::*TMethod)(A0 a0, A1 a1)>
    static delegate from_method(T* object_ptr)
    {
        delegate d;
        d.object_ptr = object_ptr;
        d.stub_ptr = &method_stub<T, TMethod>;
        return d;
    }

    void operator()(A0 a0, A1 a1) const
    {
        if (!object_ptr)
            return;
        return stub_ptr(object_ptr, a0, a1);
    }
    
    operator bool() const { return object_ptr != NULL; }

private:
    typedef void (*stub_type)(void* object_ptr, A0 a0, A1 a1);

    void* object_ptr;
    stub_type stub_ptr;
    
    template <class T, void (T::*TMethod)(A0 a0, A1 a1)>
    static void method_stub(void* object_ptr, A0 a0, A1 a1)
    {
        T* p = static_cast<T*>(object_ptr);
        return (p->*TMethod)(a0, a1);
    }
};

#define DELEGATE(DelegateType, Type, Object, Method) (DelegateType::from_method<Type, &Type::Method>(&Object))
              
template<typename A0=void, typename A1=void>
class rdelegate
{
public:
    rdelegate() : object_ptr(NULL), stub_ptr(NULL)
    {
    }

    template <class T, A0 (T::*TMethod)(A1 a1)>
    static rdelegate from_method(T* object_ptr)
    {
        rdelegate d;
        d.object_ptr = object_ptr;
        d.stub_ptr = &method_stub<T, TMethod>;
        return d;
    }

    A0 operator()(A1 a1) const
    {
        if (!object_ptr)
            return a1;
        return stub_ptr(object_ptr, a1);
    }
    
    operator bool() const { return object_ptr != NULL; }

private:
    typedef A0 (*stub_type)(void* object_ptr, A1 a1);

    void* object_ptr;
    stub_type stub_ptr;
    
    template <class T, A0 (T::*TMethod)(A1 a1)>
    static A0 method_stub(void* object_ptr, A1 a1)
    {
        T* p = static_cast<T*>(object_ptr);
        return (p->*TMethod)(a1);
    }
};

#define RDELEGATE(DelegateType, Type, Object, Method) (DelegateType::from_method<Type, &Type::Method>(&Object))
              
#endif//DELEGATE_H
